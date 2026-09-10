"""AgentHandler v5 — handle(event, runtime) 把 event 包装推 runtime.input_queue.

设计动机 (Task #3472 v5):
- v4 问题: handle(event) 只是 stub, 实际 ES event -> user input 转换在 main.py
  的 es_dispatcher 线程里. handler 跟 dispatcher 职责混乱.
- v5 设计: handler 拿到 runtime 引用, 自己负责把 event 包装成 user input
  推到 runtime.input_queue. 不再有独立的 es_dispatcher 线程.
  Runtime 就是统一的输入总线 (user + event 一个 queue).

职责 (v5, 单一):
    1. 注册 cli-sample/tools/ 6 个工具到 SDK ToolManager
    2. 构造 StatelessReactAgent (跟 cli-sample 的 _AGENT_SETTINGS 一致)
    3. 暴露 .agent (给 main loop 用)
    4. 实现 handle(event, runtime): 把 event 包装成 user input 推 runtime.input_queue
       - 这是 v5 关键改动: handler 主动把 event 投到统一 input_queue

对比 v3 -> v4 -> v5:
| v3                                  | v4                              | v5                              |
|-------------------------------------|---------------------------------|---------------------------------|
| _mini_agent_loop (mock + real)      | 不实现, 委托 main loop           | 不实现, 委托 main loop           |
| handle(event) -> mini loop          | handle(event) 仅做 stub          | handle(event, runtime) 包装 + 推 |
| 自己调 agent.step + tool dispatch   | 不在 handler 里                 | 不在 handler 里                 |
| runtime dispatcher -> handle         | main.py es_dispatcher -> queue  | runtime.add_event -> handle     |
|                                     |                                 | -> runtime.add_user_input       |
|                                     |                                 | 单一 input_queue                |

复用 cli-sample 的逻辑:
    - cli-sample/cli_sample.py: CliSampleAgent.step() (SDK StatelessReactAgent)
    - cli-sample/cli_sample.py: main() REPL (input -> step -> print)
    - cli-sample/tools/register_default_tools() (6 个工具)
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
    """单 handler (v5): 注册工具 + 构造 agent + 包装 event -> user input.

    v5 关键改动: 实现 handle(event, runtime) — 把 event 包装成 user input
    推 runtime.input_queue. Runtime 是统一的输入总线, handler 跟 user input
    走同一条路径.

    主要属性:
        .agent: StatelessReactAgent 实例 (跟 cli-sample 一致), 供 main loop 用
        .history: 对话历史 (agent 内部的, 我们不维护自己的)

    主要方法:
        .handle(event, runtime): v5 新签名 — 接收 runtime, 推 input_queue
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
    # v5 新签名: handle(event, runtime)
    # ==================================================================

    def handle(self, event: Any, runtime: Any) -> None:
        """v5: handler 接收 runtime, 把 event 包装成 user input 推到 runtime.input_queue.

        这是 v5 关键改动 ——
        - handler 不再调 agent.step (避免重复处理)
        - handler 把 event 翻译成 user input 字符串, 推 runtime.input_queue
        - cli loop 从 runtime.input_queue 拿 (跟 user input 完全一样)
        - agent 处理时不区分来源 (走同一条 agent.step() 路径)

        Args:
            event: Event 实例 (type/source/payload/timestamp)
            runtime: EventSourceRuntime 实例 (用来 add_user_input / input_queue)
        """
        user_input = self._event_to_user_input(event)
        logger.info(
            "[%s] ES event -> user input (origin=es_event:%s): %s",
            self.name,
            event.source,
            user_input[:120].replace("\n", " | "),
        )
        # v5: 推到 runtime.input_queue, 跟 user input 走同一条路径
        runtime.add_user_input(user_input, source_tag=f"es_event:{event.source}")

    def _event_to_user_input(self, event: Any) -> str:
        """把 Event 包装成 user input 字符串 (跟 v4 一致的格式)."""
        return (
            f"[ES 自动输入] 我收到了一个定时事件:\n"
            f"  - type: {event.type}\n"
            f"  - source: {event.source}\n"
            f"  - payload: {event.payload}\n"
            f"  - timestamp: {event.timestamp}\n"
            f"请利用可用工具 (bash / write_file / read_file 等) 处理这个事件."
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