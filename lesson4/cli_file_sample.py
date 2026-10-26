#!/usr/bin/env python3
"""
cli_file_sample: Lesson 4 — 仿照 cli-sample 重写的本地文件 CLI Agent

与 ../cli-sample/cli_sample.py 的关系: 结构相同 (REPL + Agent 薄壳 +
StatelessReactAgent + 本地 tools/ 包), 代码**自己重写**:
- tools/: 6 个本地工具 (read_file 已给样例, 其余 5 个 TODO(1)-(5))
- 注册:   tools/__init__.py 的 register_default_tools() (TODO(6))
- 接线:   本文件的 TODO(7)(8)

SDK 负责的 (黑盒, 读 reference/ 理解): LLM 调用 + function calling 解析 +
工具分发 + 结果回填 + 多轮 tool 循环 — 全在 StatelessReactAgent.step() 里.

预期演示:
    >>> 在 /tmp/lesson4-demo 下创建 notes.md，写入"今天学了 ReAct 循环"
    （模型选 write_file -> 工具真实执行 -> 模型给出最终回答）
    >>> exit

用法 (lesson4 自己的环境, 见 README 第 0 步; .env 沿用 ../cli-sample 的):
    cd lesson4 && python cli_file_sample.py
"""
from __future__ import annotations

import importlib.metadata
import os
import sys
from pathlib import Path
from typing import Any, Iterator

# ------------------------------------------------------------
# sys.path: lesson4/ (本课 tools 包; 不再用 ../cli-sample 的工具)
# ------------------------------------------------------------
_LESSON4_DIR = Path(__file__).resolve().parent
if str(_LESSON4_DIR) not in sys.path:
    sys.path.insert(0, str(_LESSON4_DIR))

# 同 cli_sample.py: 规避 mcp 包 metadata 探测问题
_orig_version = importlib.metadata.version


def _safe_version(name: str) -> str:
    try:
        return _orig_version(name)
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


importlib.metadata.version = _safe_version

# .env 加载 (同 cli_sample.py, 必须在 SDK import 之前; override=True 让 .env 优先)
from dotenv import load_dotenv  # noqa: E402

for _env in (_LESSON4_DIR.parent / "cli-sample" / ".env", _LESSON4_DIR / ".env"):
    if _env.exists():
        load_dotenv(_env, override=True)
        break

# ------------------------------------------------------------
# TongAgent SDK imports
# ------------------------------------------------------------
from tongagents.agent import Agent, AgentSettings  # noqa: E402
from tongagents.agents.llm import ModelConfig, ModelProvider  # noqa: E402
from tongagents.agents.llm_agent import (  # noqa: E402
    ReactAgentSetting,
    StatelessReactAgent,
)
from tongagents.agents.llm_agent.defs import LLMInputEvent  # noqa: E402
from tongagents.agents.llm.messages import UserPromptMessage  # noqa: E402
from tongagents.tools.tool_manager import ToolManager  # noqa: E402

# 本课学生实现的工具
from tools import register_default_tools  # noqa: E402

# ============================================================
# System Prompt (已给): 直接答普通问题, 文件操作必须调工具
# ============================================================
_SYSTEM_PROMPT = (
    "你是本地文件操作 agent, 帮用户读写、编辑、搜索本地文件, 也可执行 shell 命令. "
    "普通问题直接回答; 文件/命令操作必须调用工具, 拿到工具结果后再回答. 用中文回答."
)

SETTINGS = AgentSettings(
    name="lesson4-file-agent",
    description="Lesson 4 作业: 自己重写的本地文件 CLI Agent",
    capabilities=["chat", "file-ops"],
    model=os.getenv("OPENAI_MODEL", "gpt-4"),
)


# ============================================================
# Agent 子类: 薄壳包 StatelessReactAgent.step()
# ============================================================
class CliFileAgent(Agent):
    """自己重写的 CLI Agent: 内部用 SDK 的 StatelessReactAgent 跑 LLM.

    对照 cli_sample.py 的 CliSampleAgent — 结构完全一致,
    构造参数 (TODO(7)) 和返回值提取 (TODO(8)) 由你亲手接上.
    """

    agent_setting = SETTINGS

    def __init__(self):
        super().__init__(agent_setting=SETTINGS)
        # TODO(7): 构造 self._agent = StatelessReactAgent(agent_settings=...)
        #
        # 提示 (对照 reference/stateless_react_agent.py 的 __init__:
        #       tool_identifier_list 里的每个名字都会去 ToolManager 取实例):
        #   self._agent = StatelessReactAgent(
        #       agent_settings=ReactAgentSetting(
        #           name="lesson4-file-agent",
        #           llm_config=ModelConfig(
        #               model_provider=ModelProvider.OPENAI_COMPATIBLE
        #           ),  # SDK 从 env 读 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
        #           tool_identifier_list=list(ToolManager.tool_classes.keys()),
        #           system_prompt=_SYSTEM_PROMPT,
        #       )
        #   )
        raise NotImplementedError("Lesson 4 TODO(7): 构造 StatelessReactAgent")

    def step(self, event: Any) -> str:
        """TODO(8): 处理单条 query, 调 SDK agent.step() → 返回最终文本.

        StatelessReactAgent.step() 返回 list[Action] — 一轮 ReAct 循环里
        产生的 ToolAction / TextAction 都在里面, 你要挑出**最终回复**:
        - is_final_response=True 的 TextAction, 其 content 是最终回复
        - 找不到时退而求其次: 第一个有 content 的 action
        - 都没有返回 ""
        """
        wrap = LLMInputEvent(input=[UserPromptMessage(str(event))])
        actions = self._agent.step(wrap)
        # TODO(8): 删除下面两行, 按上面注释提取最终文本并 return
        _ = actions
        raise NotImplementedError("Lesson 4 TODO(8): 实现 step 的返回值提取")

    def run(self, events: Iterator[Any]) -> Iterator[str]:
        """流式处理多个事件, 每条产生一个回复."""
        for event in events:
            yield self.step(event)

    async def astep(self, event: Any) -> str:
        """异步单步处理 (用 sync agent.step, 不真异步)."""
        return self.step(event)

    async def arun(self, events: Any) -> Any:
        """异步流式处理."""
        for event in events:
            yield await self.astep(event)


# ============================================================
# REPL 入口
# ============================================================
BANNER = """
============================================================
  lesson4: 自己重写的本地文件 CLI Agent (SDK ReAct 循环)
============================================================
  Agent:  StatelessReactAgent (SDK)
  工具:   {tool_count} 个本地工具 ({tool_names})
  模型:   {model}
  端点:   {base_url}
============================================================
  试试: 在 /tmp/lesson4-demo 下创建 notes.md，写入"今天学了 ReAct 循环"
  退出: exit / quit / Ctrl+D
============================================================
""".strip()


def main() -> None:
    try:
        register_default_tools()
    except NotImplementedError as e:
        print(f"[提示] 先完成 TODO(6): {e}")
        sys.exit(1)

    try:
        cli = CliFileAgent()
    except NotImplementedError as e:
        print(f"[提示] 先完成 TODO(7): {e}")
        sys.exit(1)

    print(
        BANNER.format(
            tool_count=len(ToolManager.tool_classes),
            tool_names=", ".join(sorted(ToolManager.tool_classes)),
            model=os.environ.get("OPENAI_MODEL", "(unset)"),
            base_url=os.environ.get("OPENAI_BASE_URL", "(default)"),
        )
    )

    try:
        while True:
            try:
                query = input(">>> ").strip()
            except EOFError:
                print()
                break
            if not query:
                continue
            if query.lower() in ("exit", "quit", "q"):
                break

            try:
                response = cli.step(query)
                print(f"  {response}")
            except NotImplementedError as e:
                print(f"  [提示] 还有 TODO 未完成: {e}")
            except Exception as e:  # noqa: BLE001
                print(f"  [error] {type(e).__name__}: {e}")
            print()
    except KeyboardInterrupt:
        print("\n[interrupted]")

    print("bye!")


if __name__ == "__main__":
    main()
