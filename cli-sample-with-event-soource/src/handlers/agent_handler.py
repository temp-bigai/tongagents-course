"""AgentHandler (v4) - 复用 cli-sample 的 agent, 不做 mini loop.

设计动机 (Task #3470):
- 用户反馈 v3 (Task #3469) 太复杂: AgentHandler 自己实现 _mini_agent_loop /
  _call_real_llm_loop / _execute_tool / _mock_llm_loop, 跟 cli-sample 的"单步
  step(query) -> 拿 final response"循环重复造轮子.
- "还是不符合我的预期, handler 里面就保留使用到的 handler 就好, 一个就行,
   另外需要用 cli-sample 里面的命令行中的等待用户 input 和输出 agent response
   的循环逻辑"
- v4 设计: AgentHandler 只做一件事 — 提供一个 agent (跟 cli-sample 一样的
  StatelessReactAgent). 不在 handler 内部调 agent.step, 不在 handler 内部做
  tool dispatch, 不在 handler 内部做 mock fallback.
  这一切都委托给 cli-sample 的 REPL 循环: input -> agent.step -> print.

职责 (v4, 单一):
    1. 注册 cli-sample/tools/ 6 个工具到 SDK ToolManager
    2. 构造 StatelessReactAgent (跟 cli-sample 的 _AGENT_SETTINGS 一致)
    3. 暴露 .agent (给 main loop 用)
    4. 提供 handle(event) 兼容接口 (虽然 v4 main loop 不通过 runtime 注册 handler,
       但保留 handle 接口, 万一以后接 SDK dispatcher 用得上)

对比 v3 -> v4:
| v3                                  | v4                              |
|-------------------------------------|---------------------------------|
| _mini_agent_loop (mock + real 双路径) | 不实现, 由 main loop 走 cli-sample 循环 |
| _call_real_llm_loop + SDK dispatch | 不实现                          |
| _mock_llm_loop + 自写简易工具       | 不实现                          |
| _bash_tool / _write_file_tool / ...  | 不实现 (用 SDK 工具)             |
| handle(event) -> mini loop          | handle(event) 只做 mock 提示     |
| runtime 注册 handler + bind         | runtime 不注册 handler, 只 dispatch |
|                                     | event 到 input_queue, 然后走 user input loop |

复用 cli-sample 的逻辑:
    - cli-sample/cli_sample.py: CliSampleAgent.step() (SDK StatelessReactAgent)
    - cli-sample/cli_sample.py: main() REPL (input -> step -> print)
    - cli-sample/tools/register_default_tools() (6 个工具)

v4 的 main.py 完全模仿 cli-sample 的 REPL 模式, 只是 input 来源多了 ES 注入.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, List

logger = logging.getLogger("handler.agent")


# cli-sample 根目录 (用来: 1) 注册 cli-sample/tools 到 SDK ToolManager;
#                       2) 复用 cli-sample 的 CliSampleAgent 构造模式)
_CLI_SAMPLE_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "cli-sample"
)
_CLI_SAMPLE_TOOLS_DIR = _CLI_SAMPLE_DIR / "tools"


def _register_cli_sample_tools() -> bool:
    """把 cli-sample/tools/ 的 6 个工具注册到 tongagents.ToolManager.

    返回 True 成功, False 失败 (SDK 缺失 / cli-sample/tools/ 找不到 / import 失败).
    """
    try:
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

    # cli-sample/tools/__init__.py 用 `from tools import register_default_tools`,
    # 需要 cli-sample/ 在 sys.path. 这里把它加进去.
    if str(_CLI_SAMPLE_DIR) not in sys.path:
        sys.path.insert(0, str(_CLI_SAMPLE_DIR))

    try:
        from tools import register_default_tools  # type: ignore  # noqa: E402
    except ImportError as e:
        logger.warning("[agent] import cli-sample/tools 失败: %s", e)
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
    """单 handler (v4): 只负责注册工具 + 构造 agent, 不实现 mini loop.

    v4 设计: 不在 handler 里调 agent.step, 不在 handler 里 dispatch tool,
    不在 handler 里 mock LLM. 这一切都委托给 cli-sample 的 REPL 循环
    (在 main.py 里, 复用 cli_sample.py 的 main() 结构).

    主要属性:
        .agent: StatelessReactAgent 实例 (跟 cli-sample 一致), 供 main loop 用
        .history: 对话历史 (agent 内部的, 我们不维护自己的)

    兼容接口:
        .handle(event): 万一以后接 SDK dispatcher (runtime.add_handler + bind),
        也可以直接调. v4 main loop 不依赖它, 仅作为兼容 stub.
    """

    def __init__(
        self,
        name: str = "agent_runner",
        system_prompt: str | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt or self._default_system_prompt()

        # 1. 注册 cli-sample 工具 (跟 cli-sample 一致)
        self._tools_registered = _register_cli_sample_tools()

        # 2. 构造 agent (跟 cli-sample 一样)
        self.agent = self._build_cli_sample_agent()

    # ==================================================================
    # Agent 构造 (复用 cli-sample/cli_sample.py 模式)
    # ==================================================================

    def _build_cli_sample_agent(self) -> Any:
        """构造 SDK StatelessReactAgent (跟 cli-sample/cli_sample.py 一致).

        直接复用 cli-sample 的 _AGENT_SETTINGS 模式:
        - ModelConfig(OPENAI_COMPATIBLE) — SDK 从 env 读 OPENAI_* 三件套
        - tool_identifier_list = ToolManager.tool_classes 的 keys (cli-sample 6 个工具)
        - system_prompt — 跟 cli-sample 风格一致
        """
        try:
            from tongagents.agents.llm_agent import (  # type: ignore
                StatelessReactAgent,
                ReactAgentSetting,
            )
            from tongagents.agents.llm import ModelConfig, ModelProvider  # type: ignore
            from tongagents.tools.tool_manager import ToolManager  # type: ignore
        except ImportError:
            logger.error(
                "[%s] ❌ tongagents SDK 不可用 — 无法构造 agent. "
                "请先 pip install tongagents.",
                self.name,
            )
            raise

        tool_ids = list(ToolManager.tool_classes.keys()) if self._tools_registered else []
        settings = ReactAgentSetting(
            name=f"{self.name}_cli_es_agent",
            llm_config=ModelConfig(model_provider=ModelProvider.OPENAI_COMPATIBLE),
            tool_identifier_list=tool_ids,
            system_prompt=self.system_prompt,
        )
        agent = StatelessReactAgent(agent_settings=settings)
        logger.info(
            "[%s] ✅ StatelessReactAgent 已构造 (复用 cli-sample 模式, tools=%d)",
            self.name,
            len(tool_ids),
        )
        return agent

    # ==================================================================
    # Public API
    # ==================================================================

    def handle(self, event: Any) -> None:
        """兼容接口 (runtime.add_handler 后, dispatcher 会调).

        v4 main loop 不通过 runtime 注册 handler (event 走 input_queue ->
        cli loop). 这个 handle 仅做日志 + 提示, 不实际调 agent.step (避免
        重复处理 — main loop 已经把 event 当 user input 跑了).

        如果以后要"runtime 直接 dispatch 到 handler"模式, 在这里调 agent.step
        即可 (跟 cli-sample 的 CliSampleAgent.step 同形态).
        """
        logger.info(
            "[%s] handle() 收到事件 %s (v4 仅做兼容提示, 不调 agent.step; "
            "请用 main loop 把 event 当 user input 跑)",
            self.name,
            event,
        )

    # ==================================================================
    # 配置
    # ==================================================================

    def _default_system_prompt(self) -> str:
        """默认 system prompt (跟 cli-sample 一致)."""
        return (
            "你是 cli-sample-with-event-soource agent, 帮用户处理本地文件 "
            "(读 / 写 / 列 / 搜) 和定时事件. "
            "普通问题直接答, 文件操作必须调工具. 用中文回答. "
            "事件来源有两种: 用户在命令行输入, 或后台定时器触发, 都当作用户输入处理."
        )

    @property
    def history(self) -> List[Any]:
        """透传 agent 内部的 history (如果有)."""
        return getattr(self.agent, "history", [])
