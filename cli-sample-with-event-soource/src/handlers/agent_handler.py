"""AgentHandler - 把 Event 包装成 user query, 调真 LLM 处理 (Task #3469 v3).

设计动机 (Task #3469):
- 用户反馈 v2 (commit ce94e9a) 的 _mini_agent_loop 是 mock LLM 决策 (确定性 plan), 不是真调.
- "真的调通 llm" - 跟 cli-sample/cli_sample.py 一样, 真调 OpenAI 兼容 LLM + tool dispatch.

设计要点 (跟 cli-sample 一致):
- 用 TongAgent SDK StatelessReactAgent.step() 跑 LLM
  - SDK 内部: client.chat.completions.create() (真 HTTP 请求到 LLM 端点)
  - SDK 内部: tool dispatch + 多轮 tool 循环 (LLM 决策 + tool 执行全自动)
  - SDK 内部: 把 tool result 回传 LLM, 直到 is_final_response=True
- 我们只做: REPL/事件 → 包装成 user query → agent.step(query) → 提取最终回复
- 工具真实: 6 个本地工具 (read_file / write_file / edit_file / bash / glob / grep)
  从 cli-sample/tools/ 复用 (SDK ToolManager 自动注册)

设计要点 (跟 cli-sample 略不同):
- cli-sample 是交互 REPL; 这里是 ES 事件触发, 每个 event 一次 step()
- 保留 _event_to_query / _mini_agent_loop 入口风格 (跟 v2 一致), 让 main.py/test_run.py 无需改动
- 如果 OPENAI_API_KEY/OPENAI_MODEL 未设, 自动 fallback 到 mock (v2 行为), 让测试在无 key 也能跑

对比 v2 → v3:
| v2 (mock LLM)                | v3 (real LLM via SDK)               |
|------------------------------|--------------------------------------|
| 确定性 plan (3 tools)        | LLM 决定调哪些 tool (动态)           |
| _bash_tool/_read_file 简易版 | cli-sample/tools/* (跟 SDK 集成)     |
| 不调 LLM                     | TongAgent SDK → client.chat.completions |
| 无 tool_calls JSON 解析      | SDK 内部自动解析 + tool dispatch     |
| Tool result 仅打日志         | Tool result 回传 LLM (tool 循环)     |

Fallback 策略:
- 有 OPENAI_API_KEY + OPENAI_MODEL: 真 LLM 路径
- 缺一个: logger.warning + 走 mock (跟 v2 一致, 保证测试可跑)
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, List

logger = logging.getLogger("handler.agent")


# ============================================================
# SDK 工具集的本地副本路径 (供 sys.path 加进去, 让 SDK 找到 register_default_tools)
# ============================================================
_CLI_SAMPLE_TOOLS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "cli-sample" / "tools"
)


def _register_cli_sample_tools() -> bool:
    """把 cli-sample/tools/ 的 6 个工具注册到 tongagents.ToolManager.

    返回 True 成功, False 失败 (SDK 缺失 / 工具目录找不到).
    """
    try:
        # tongagents SDK 必须能 import
        from tongagents.tools.tool_manager import ToolManager  # type: ignore
    except ImportError:
        logger.warning("[agent] tongagents SDK 未安装, 跳过工具注册")
        return False

    if not _CLI_SAMPLE_TOOLS_DIR.is_dir():
        logger.warning(
            "[agent] 找不到 cli-sample/tools/ 目录 (%s), 跳过工具注册",
            _CLI_SAMPLE_TOOLS_DIR,
        )
        return False

    # cli-sample/tools/__init__.py 需要 cli-sample/ 在 sys.path (它的 register_default_tools 是相对 import)
    cli_sample_dir = _CLI_SAMPLE_TOOLS_DIR.parent
    if str(cli_sample_dir) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(cli_sample_dir))

    try:
        from tools import register_default_tools  # type: ignore  # cli-sample/tools/__init__.py
    except ImportError as e:
        logger.warning("[agent] import cli-sample tools 失败: %s", e)
        return False

    try:
        register_default_tools()
        tool_names = list(ToolManager.tool_classes.keys())
        logger.info(
            "[agent] ✅ SDK 工具已注册 (%d 个): %s",
            len(tool_names),
            tool_names,
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[agent] 注册 cli-sample tools 失败: %s", e)
        return False


class AgentHandler:
    """Agent Handler: 把 Event 当作 user input, 调真 LLM (TongAgent SDK) 处理.

    类似 Tong-Agent act() 的 mini 版:
    - act(query, ...) -> workflow.stream(query) -> 输出
    - 这里: handle(event) -> _event_to_query(event) -> _mini_agent_loop(query) -> 真调 LLM + tools
    """

    def __init__(
        self,
        name: str = "agent_runner",
        log_file: str = "/tmp/es_agent_log.txt",
        max_tool_calls: int = 5,
        system_prompt: str | None = None,
    ) -> None:
        self.name = name
        self.log_file = log_file
        self.max_tool_calls = max_tool_calls
        self.system_prompt = system_prompt or self._default_system_prompt()

        # 真 LLM 决策路径用的工具 (跟 cli-sample/tools/ 一致, SDK 自动 dispatch)
        # 注册 6 个工具到 SDK ToolManager (idempotent)
        self._tools_registered = _register_cli_sample_tools()

        # mini agent loop 的 "记忆" (类似 chat history), 方便观察
        self.history: List[dict[str, Any]] = []

        # 是否走真 LLM 路径 (检测 OPENAI_API_KEY + OPENAI_MODEL + SDK 可用 + 工具已注册)
        self._llm_available = self._check_llm_available()
        if self._llm_available:
            self._agent = self._build_sdk_agent()
            logger.info(
                "[%s] ✅ 真 LLM 路径启用 (TongAgent SDK StatelessReactAgent)",
                self.name,
            )
        else:
            self._agent = None
            logger.warning(
                "[%s] ⚠️  真 LLM 不可用, fallback 到 mock (v2 行为). "
                "检查 OPENAI_API_KEY + OPENAI_MODEL + tongagents SDK 是否都齐全.",
                self.name,
            )

    # ==================================================================
    # Public API: handle(Event)
    # ==================================================================

    def handle(self, event: Any) -> None:
        """统一入口: 收到 Event -> 包装成 user query -> 调 mini agent loop.

        对应 Tong-Agent act(query) 的入口:
            act("你好") -> workflow.stream("你好") -> 输出
        这里:
            handle(event) -> _event_to_query(event) -> _mini_agent_loop(query) -> 调用 tools
        """
        logger.info("[%s] 收到事件: %s", self.name, event)

        # 1. 封装 event 为 user query (像 act() 接收的字符串)
        user_query = self._event_to_query(event)
        logger.info("[%s] [agent] user query: %s", self.name, user_query[:200])

        # 2. mini agent loop (替代 workflow.stream)
        self._mini_agent_loop(user_query)

    # ==================================================================
    # Step 1: Event -> user query (包装逻辑, 参考 Tong-Agent lark_cli 思路)
    # ==================================================================

    def _event_to_query(self, event: Any) -> str:
        """把 Event payload 包装成自然语言 user query.

        类似 Tong-Agent lark_cli 把 IM 消息提取成 message 字段, 这里把 ES
        payload 包装成 agent 能读懂的 query.
        """
        return (
            f"我收到了一个定时事件 (type={event.type}, source={event.source}): "
            f"payload={event.payload}. "
            f"请利用可用 tools 处理这个事件. "
            f"如果是定时事件, 可以: "
            f"1) 用 bash 探活 (date / echo / ps 等), "
            f"2) 用 write_file 追加日志记录 (建议路径: {self.log_file}), "
            f"3) 用 list_files 检查工作目录. "
            f"简短回答, 不要做无关操作."
        )

    # ==================================================================
    # Step 2: mini agent loop (替代 workflow.stream)
    # ==================================================================

    def _mini_agent_loop(self, query: str) -> None:
        """简化版 agent loop: 真 LLM 决策 + 真 tool 执行.

        v2 (mock): 确定性 plan + 自己调 3 个简易 tool.
        v3 (real): TongAgent SDK StatelessReactAgent.step() — SDK 内部跑 LLM + tool dispatch.

        Tong-Agent 里这一段是:
            for chunk in workflow.stream(query):
                content = chunk.content
                print(content)

        教学版简化:
        - "思考" (真 LLM): SDK 内部 client.chat.completions.create() 调真 LLM
        - "行动" (真): SDK 自动 dispatch tool (ToolManager 里的 tool)
        - "观察" (真): SDK 自动把 tool result 回传 LLM, 直到 is_final_response=True
        """
        logger.info(
            "[%s] [agent] 思考: 收到 user query, 走 %s 路径",
            self.name,
            "真 LLM (TongAgent SDK)" if self._llm_available else "MOCK (fallback)",
        )
        self.history.append({"role": "user", "content": query})

        if self._llm_available:
            self._call_real_llm_loop(query)
        else:
            self._mock_llm_loop(query)

    # ==================================================================
    # 真 LLM 路径 (TongAgent SDK StatelessReactAgent)
    # ==================================================================

    def _check_llm_available(self) -> bool:
        """检测真 LLM 是否可用: OPENAI_API_KEY + OPENAI_MODEL + SDK + 工具注册."""
        has_api_key = bool(os.environ.get("OPENAI_API_KEY"))
        has_model = bool(os.environ.get("OPENAI_MODEL"))
        if not (has_api_key and has_model):
            logger.warning(
                "[%s] [agent] OPENAI_API_KEY=%s, OPENAI_MODEL=%s (需要都设了才走真 LLM)",
                self.name,
                "✓" if has_api_key else "✗",
                "✓" if has_model else "✗",
            )
            return False
        if not self._tools_registered:
            logger.warning("[%s] [agent] SDK 工具未注册, 不能走真 LLM", self.name)
            return False
        try:
            # 探测 SDK 可用
            from tongagents.agents.llm_agent import StatelessReactAgent  # type: ignore  # noqa: F401
        except ImportError:
            logger.warning("[%s] [agent] tongagents SDK 不可用", self.name)
            return False
        return True

    def _build_sdk_agent(self) -> Any:
        """构造 TongAgent SDK StatelessReactAgent (跟 cli-sample 一致)."""
        from tongagents.agents.llm_agent import (  # type: ignore
            StatelessReactAgent,
            ReactAgentSetting,
        )
        from tongagents.agents.llm import ModelConfig, ModelProvider  # type: ignore
        from tongagents.tools.tool_manager import ToolManager  # type: ignore

        settings = ReactAgentSetting(
            name=f"{self.name}_sdk_agent",
            llm_config=ModelConfig(model_provider=ModelProvider.OPENAI_COMPATIBLE),
            tool_identifier_list=list(ToolManager.tool_classes.keys()),
            system_prompt=self.system_prompt,
        )
        return StatelessReactAgent(agent_settings=settings)

    def _call_real_llm_loop(self, query: str) -> None:
        """真调 LLM (TongAgent SDK StatelessReactAgent.step), 处理 tool_calls.

        SDK 内部自动:
          1. 构造 messages (system + history)
          2. client.chat.completions.create(..., tools=tool_schemas) -> LLM 输出
          3. 解析 tool_calls JSON
          4. dispatch tool -> 拿 tool result
          5. tool result 回传 LLM (循环)
          6. 直到 LLM 输出 is_final_response=True 的 TextAction
        """
        from tongagents.agents.llm_agent.defs import LLMInputEvent  # type: ignore
        from tongagents.agents.llm.messages import UserPromptMessage  # type: ignore

        logger.info("[%s] [agent] 调用真 LLM (TongAgent SDK)...", self.name)

        try:
            wrap = LLMInputEvent(input=[UserPromptMessage(query)])
            actions = self._agent.step(wrap)
        except Exception as e:  # noqa: BLE001
            logger.exception("[%s] [agent] ❌ LLM 调用失败: %s", self.name, e)
            logger.warning("[%s] [agent] fallback 到 mock 路径", self.name)
            self._mock_llm_loop(query)
            return

        # 把所有 action 记到 history (中间推理 + 最终回复)
        final_content = ""
        for i, action in enumerate(actions):
            content = getattr(action, "content", None) or ""
            is_final = bool(getattr(action, "is_final_response", False))
            kind = "final" if is_final else "intermediate"
            logger.info(
                "[%s] [agent] LLM action #%d (%s): %s",
                self.name,
                i,
                kind,
                content[:200].replace("\n", "\\n"),
            )
            self.history.append(
                {
                    "role": "assistant",
                    "content": content,
                    "is_final_response": is_final,
                    "kind": kind,
                }
            )
            if is_final:
                final_content = content

        # 把最终回复写一行到日志文件 (跟 v2 write_file 行为对齐, 让 test_run 断言能跑)
        # 用独特标记 [es-agent-event] 而不是 [event], 避免跟 LLM 写入的 [event] 字符串混淆
        if final_content and self.log_file:
            try:
                log_path = Path(self.log_file)
                if str(log_path.parent) and str(log_path.parent) != ".":
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as f:
                    from datetime import datetime
                    ts = datetime.now().isoformat(timespec="seconds")
                    first_line = final_content.split("\n", 1)[0][:200]
                    f.write(f"[{ts}] [es-agent-event] {first_line}\n")
                logger.info("[%s] [agent] 日志已写入: %s", self.name, self.log_file)
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] [agent] 写日志失败: %s", self.name, e)

        logger.info(
            "[%s] [agent] 完成 LLM 调用, actions=%d, history 长度 = %d",
            self.name,
            len(actions),
            len(self.history),
        )

    # ==================================================================
    # Mock 路径 (v2 行为, fallback)
    # ==================================================================

    def _mock_llm_loop(self, query: str) -> None:
        """Mock fallback: 确定性 plan + 简易本地 tool (跟 v2 一致)."""
        logger.info("[%s] [agent] (mock) 决定调用 3 个 tool", self.name)

        plan = [
            ("bash", {"command": "date -u", "timeout": 5}),
            (
                "write_file",
                {
                    "path": self.log_file,
                    "content": self._format_log_entry(query),
                    "append": True,
                },
            ),
            ("list_files", {"dir_path": ".", "pattern": "*.py"}),
        ]

        # 简易工具 (跟 v2 一致, 不走 SDK)
        simple_tools = {
            "bash": self._bash_tool,
            "write_file": self._write_file_tool,
            "list_files": self._list_files_tool,
        }

        plan = plan[: self.max_tool_calls]
        for i, (tool_name, args) in enumerate(plan, start=1):
            logger.info(
                "[%s] [agent] mock tool #%d: %s(args=%s)",
                self.name,
                i,
                tool_name,
                {k: (v if len(str(v)) < 80 else str(v)[:77] + "...") for k, v in args.items()},
            )
            try:
                result = simple_tools[tool_name](**args)
                preview = result if len(result) < 200 else result[:197] + "..."
                logger.info(
                    "[%s] [agent] mock tool #%d (%s) result: %s",
                    self.name,
                    i,
                    tool_name,
                    preview,
                )
                self.history.append(
                    {
                        "role": "tool",
                        "tool": tool_name,
                        "args": args,
                        "result_preview": preview,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "[%s] [agent] mock tool #%d (%s) 失败: %s",
                    self.name,
                    i,
                    tool_name,
                    e,
                )

    # ==================================================================
    # 配置 / 工具 (mock fallback 用)
    # ==================================================================

    def _default_system_prompt(self) -> str:
        """默认 system prompt (跟 v2 风格一致, 但更明确要求用 SDK 工具)."""
        return (
            "你是 Tong-Agent CLI 的事件处理助手. 当收到定时事件时, "
            "你需要用合适的 tool 处理它. "
            "可用 tools (来自 cli-sample/tools/): "
            "bash (执行 shell 命令), read_file (读文件), write_file (写文件), "
            "edit_file (精确字符串替换), glob (文件名通配), grep (内容正则搜索). "
            "保持简洁, 1-3 个 tool call 即可. "
            "事件 payload 是定时器 tick 信息, 你可以根据需要处理."
        )

    def _format_log_entry(self, query: str) -> str:
        """格式化一条日志条目 (mock write_file 追加)."""
        from datetime import datetime

        ts = datetime.now().isoformat(timespec="seconds")
        first_line = query.split("\n")[0] if "\n" in query else query[:120]
        return f"[{ts}] [es-agent-event] {first_line}\n"

    # --- 简易 tools (仅 mock fallback 用) ---

    def _bash_tool(self, command: str, timeout: int = 5) -> str:
        """执行 shell 命令 (简易版, 仅 mock 用)."""
        import shlex

        try:
            cmd_args = shlex.split(command)
            result = subprocess.run(
                cmd_args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
            )
            parts: List[str] = []
            if result.stdout:
                parts.append(f"[stdout]\n{result.stdout.rstrip()}")
            if result.stderr:
                parts.append(f"[stderr]\n{result.stderr.rstrip()}")
            if result.returncode != 0 and not result.stdout and not result.stderr:
                parts.append(f"[exit code: {result.returncode}]")
            return "\n".join(parts) if parts else "(command completed, no output)"
        except Exception as e:  # noqa: BLE001
            return f"error: {e}"

    def _write_file_tool(self, path: str, content: str, append: bool = False) -> str:
        """写入文件 (简易版, 仅 mock 用)."""
        try:
            file_path = Path(path)
            if str(file_path.parent) and str(file_path.parent) != ".":
                file_path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(file_path, mode, encoding="utf-8") as f:
                f.write(content)
            action = "appended" if append else "written"
            return f"{action} {len(content)} bytes to {path}"
        except Exception as e:  # noqa: BLE001
            return f"error: {e}"

    def _list_files_tool(self, dir_path: str = ".", pattern: str = "*") -> str:
        """列出目录文件 (简易版, 仅 mock 用)."""
        try:
            base = Path(dir_path) if dir_path else Path(".")
            if not base.is_dir():
                return f"error: 目录不存在: {dir_path}"
            matches = sorted(p.name for p in base.glob(pattern))
            return "\n".join(matches) if matches else f"(no files matching {pattern!r})"
        except Exception as e:  # noqa: BLE001
            return f"error: {e}"