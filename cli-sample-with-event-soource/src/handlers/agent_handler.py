"""AgentHandler - 把 Event 包装成 user query, 调用 mini agent 处理.

设计动机 (Task #3468):
- 用户反馈 v1 (CliEventHandler) 只打印日志, 不够. 需要走 agent 流程.
- 参考 Tong-Agent cli 的 act() 函数: 把 user query 喂给 workflow.stream(query).
- 参考 Tong-Agent lark_cli handler: 把 event payload 提取 + 转成 user input.

设计要点:
- 收到 Event 后, 先把 event 包装成自然语言 user query (像 act() 接收字符串)
- 然后跑一个简化版 mini agent loop:
    - "思考" (mock LLM): 决定调用哪些 tool
    - "行动": 真实执行 bash / read_file / write_file / list_files tool
    - "观察": 把 tool 输出打日志 (模拟 LLM 看到 tool result)
- 工具真实可用 (subprocess / 文件 I/O), 不是假演示

对比 Tong-Agent:
| 本示例                          | Tong-Agent act()                       |
|---------------------------------|----------------------------------------|
| TimerEventSource                | TimerHandler                           |
| AgentHandler.handle(event)     | cli.act(query)                         |
| _event_to_query(event)         | 直接用 query (人输入)                  |
| _mini_agent_loop(query)        | workflow.stream(query) (真实 LLM)      |
| self.tools[...]()              | ToolManager 里的 tool                  |
| bash / read_file / write_file  | tongagents_cli.default_agent.tools.*     |
| 简化: mock 决策, 真实 tools     | Tong-Agent: 真实 LLM 决策 + 真实 tools |

为什么 mock LLM 决策:
- 教学示例不绑 OPENAI_API_KEY (LLM 需要)
- 但工具必须真实 (否则没法演示 agent + tool 集成的价值)
- mini agent loop 用确定性逻辑: 收到定时事件 -> bash 探活 + write_file 记录
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List

logger = logging.getLogger("handler.agent")


class AgentHandler:
    """Agent Handler: 把 Event 当作 user input, 调 mini agent loop 处理.

    类似 Tong-Agent act() 的 mini 版:
    - act(query, ...) -> workflow.stream(query) -> 输出
    - 这里: handle(event) -> _event_to_query(event) -> _mini_agent_loop(query) -> 调用 tools
    """

    def __init__(
        self,
        name: str = "agent_runner",
        log_file: str = "/tmp/es_agent_log.txt",
        max_tool_calls: int = 3,
    ) -> None:
        self.name = name
        self.log_file = log_file
        self.max_tool_calls = max_tool_calls

        # 注册可用 tools (真实可执行)
        # 用 Callable[..., str] 简化签名: 真实工具可能多参数
        self.tools: Dict[str, Callable[..., str]] = {
            "bash": self._bash_tool,
            "read_file": self._read_file_tool,
            "write_file": self._write_file_tool,
            "list_files": self._list_files_tool,
        }

        # mini agent loop 的 "记忆" (类似 chat history), 方便观察
        self.history: List[Dict[str, Any]] = []

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

        真实场景 LLM 收到的 prompt 差不多长这样:
            "我收到了一个定时事件 type=timer.tick source=sample_timer
             payload={tick: 1, source: cli-sample-with-event-soource, note: 每 30 秒触发一次}.
             请利用 tools 处理这个事件."
        """
        return (
            f"我收到了一个定时事件 (type={event.type}, source={event.source}): "
            f"payload={event.payload}. "
            f"请利用可用 tools (bash / read_file / write_file / list_files) 处理这个事件. "
            f"如果是定时事件, 可以: "
            f"1) 用 bash 探活 (echo / date), "
            f"2) 用 write_file 追加日志记录, "
            f"3) 用 list_files 检查工作目录."
        )

    # ==================================================================
    # Step 2: mini agent loop (替代 workflow.stream)
    # ==================================================================

    def _mini_agent_loop(self, query: str) -> None:
        """简化版 agent loop: 思考 -> 行动 -> 观察.

        Tong-Agent 里这一段是:
            for chunk in workflow.stream(query):
                content = chunk.content
                print(content)

        教学版简化:
        - "思考" (mock LLM): 用确定性规则决定调用哪些 tool
        - "行动" (真): 调用真实 tool, 拿到结果
        - "观察" (真): 把 tool result 打日志 + 写入 history
        """
        logger.info(
            "[%s] [agent] 思考: 收到 user query, 可用 tools = %s",
            self.name,
            list(self.tools.keys()),
        )
        self.history.append({"role": "user", "content": query})

        # ----- mock LLM 决策 -----
        # 真实 LLM 会根据 prompt + history 输出 tool_calls JSON.
        # 这里用确定性逻辑: 收到定时事件就按顺序调 3 个 tool (bash + write_file + list_files).
        # 注意: bash tool 跟 cli-sample/tools/bash_tool.py 一致, 用 shlex.split + shell=False.
        #       所以这里只能用单条命令 (不能含 && / | / ; 等 shell 语法).
        plan = [
            ("bash", {"command": "date -u", "timeout": 5}),
            ("write_file", {"path": self.log_file, "content": self._format_log_entry(query), "append": True}),
            ("list_files", {"dir_path": ".", "pattern": "*.py"}),
        ]

        # 限制 tool 调用次数, 防止无限
        plan = plan[: self.max_tool_calls]

        # ----- 行动 + 观察 -----
        for i, (tool_name, args) in enumerate(plan, start=1):
            logger.info(
                "[%s] [agent] 决定调用 tool #%d: %s(args=%s)",
                self.name,
                i,
                tool_name,
                {k: (v if len(str(v)) < 80 else str(v)[:77] + "...") for k, v in args.items()},
            )
            try:
                tool_fn = self.tools[tool_name]
                result = tool_fn(**args)
                # 截断大输出, 防止日志爆
                preview = result if len(result) < 200 else result[:197] + "..."
                logger.info(
                    "[%s] [agent] tool #%d (%s) result: %s",
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
            except Exception as e:
                logger.exception(
                    "[%s] [agent] tool #%d (%s) 失败: %s",
                    self.name,
                    i,
                    tool_name,
                    e,
                )
                self.history.append(
                    {"role": "tool", "tool": tool_name, "error": str(e)}
                )

        # ----- mock LLM 总结 -----
        logger.info(
            "[%s] [agent] 完成 %d 个 tool 调用, history 长度 = %d",
            self.name,
            len(plan),
            len(self.history),
        )

    def _format_log_entry(self, query: str) -> str:
        """格式化一条日志条目 (write_file 追加)."""
        from datetime import datetime

        ts = datetime.now().isoformat(timespec="seconds")
        # 把 query 第一行 (含 payload 摘要) 作为 entry 内容
        first_line = query.split("\n")[0] if "\n" in query else query[:120]
        return f"[{ts}] [event] {first_line}\n"

    # ==================================================================
    # Tools: 真实可执行的本地工具 (subprocess / 文件 I/O)
    #
    # 这些是简化版的 bash / read_file / write_file / list_files,
    # 跟 cli-sample/tools/ 里的同名工具功能一致, 但不走 tongagents.Tool 基类
    # (因为 mini agent loop 不需要 Tool schema, 直接 callable 即可).
    # ==================================================================

    def _bash_tool(self, command: str, timeout: int = 5) -> str:
        """执行 shell 命令 (本地直接执行, 无沙箱).

        对应 cli-sample/tools/bash_tool.py BashTool._do_call, 但更简单.
        """
        if not command:
            return "error: command 不能为空"
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
            output_parts: List[str] = []
            if result.stdout:
                output_parts.append(f"[stdout]\n{result.stdout.rstrip()}")
            if result.stderr:
                output_parts.append(f"[stderr]\n{result.stderr.rstrip()}")
            if result.returncode != 0 and not result.stdout and not result.stderr:
                output_parts.append(f"[exit code: {result.returncode}]")
            return "\n".join(output_parts) if output_parts else "(command completed, no output)"
        except ValueError as e:
            return f"error: 命令解析失败 - {e}"
        except subprocess.TimeoutExpired:
            return f"error: 命令执行超时 ({timeout}秒)"
        except FileNotFoundError as e:
            return f"error: 命令不存在 - {e}"
        except Exception as e:
            return f"error: {e}"

    def _read_file_tool(self, path: str, offset: int = 0, limit: int = 200) -> str:
        """读取文件内容 (offset/limit 范围)."""
        if not path:
            return "error: path 不能为空"
        try:
            file_path = Path(path)
            if not file_path.exists():
                return f"error: 文件不存在: {path}"
            if not file_path.is_file():
                return f"error: 路径不是文件: {path}"
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            total = len(lines)
            start = min(offset, total)
            end = min(offset + limit, total)
            content = "".join(lines[start:end])
            header = f"=== {path} (lines {start + 1}-{end}/{total}) ===\n"
            return header + "\n" + content
        except UnicodeDecodeError:
            return f"error: 文件不是 UTF-8 编码: {path}"
        except Exception as e:
            return f"error: {e}"

    def _write_file_tool(self, path: str, content: str, append: bool = False) -> str:
        """写入文件 (支持 append 追加模式)."""
        if not path:
            return "error: path 不能为空"
        try:
            file_path = Path(path)
            parent = file_path.parent
            if str(parent) and str(parent) != ".":
                parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(file_path, mode, encoding="utf-8") as f:
                f.write(content)
            action = "appended" if append else "written"
            return f"{action} {len(content)} bytes to {path}"
        except Exception as e:
            return f"error: {e}"

    def _list_files_tool(self, dir_path: str = ".", pattern: str = "*") -> str:
        """列出目录里匹配 pattern 的文件 (简化版 glob)."""
        try:
            base = Path(dir_path) if dir_path else Path(".")
            if not base.exists():
                return f"error: 目录不存在: {dir_path}"
            if not base.is_dir():
                return f"error: 路径不是目录: {dir_path}"
            matches = sorted(p.name for p in base.glob(pattern))
            if not matches:
                return f"(no files matching {pattern!r} in {dir_path})"
            return "\n".join(matches)
        except Exception as e:
            return f"error: {e}"