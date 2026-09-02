#!/usr/bin/env python3
"""
cli-sample: 用 TongAgent SDK StatelessReactAgent 的最简 CLI

仿造 Tong-Agent 的 CLI, 但极简化:
- 单文件 REPL 循环 (Read-Eval-Print)
- 调用 TongAgent SDK 的 StatelessReactAgent (同步 step() 接口, 不调 .stream())
- SDK 默认工具集 (11 个): bash / read_file / write_file / edit_file / glob / grep /
  exa_search / skill / delegate_task / query_background_process / stop_task
- 用户问"读 / 写 / 列"时 SDK 自动调对应工具
- 输入 'exit' / 'quit' / Ctrl+D 退出

**注意**: 极简 REPL 是我们自己写的; 真正的 LLM 调用 + 工具调度 + function calling
全部交给 TongAgent SDK. 我们用 SDK 的**同步**接口 `StatelessReactAgent.step()` —
直接传 user input, 拿到返回 list (通常 1 个 final TextAction, 不是 generator),
不需要管流式. SDK 自己负责多轮 tool 调用.

用法:
    # 1. 复制 Tong-Agent 的 .env (含 OPENAI_* 三件套)
    cp ~/work/codework/tong_agents/Tong-Agent/.env .env

    # 2. 装 SDK
    pip install tongagents==2.7.20 tongagents-cli python-dotenv
    #    (或 uv sync)

    # 3. 跑
    $ python cli_sample.py

环境变量 (从 .env 读, override=True 覆盖 shell env):
    OPENAI_API_KEY:   LLM key (SDK 内部用)
    OPENAI_BASE_URL:  OpenAI 兼容端点
    OPENAI_MODEL:     模型名
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

# ============================================================
# TongAgent SDK 的 mcp 子模块用 importlib.metadata.version("mcp") 探测版本,
# 但本地 pip metadata 没装 mcp, 会抛 PackageNotFoundError, 连锁 import 失败.
# 这里 monkey-patch 一下让它返回兜底版本, 绕过此 bug.
# (Tong-Agent 自己 cli/.venv 里有完整 mcp metadata, 没有这个问题)
# ============================================================
import importlib.metadata  # noqa: E402

_orig_version = importlib.metadata.version  # noqa: E402


def _safe_version(name: str) -> str:  # noqa: E402
    try:
        return _orig_version(name)
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


importlib.metadata.version = _safe_version  # noqa: E402


# ============================================================
# .env 加载 (必须在 SDK import 之前)
# ============================================================
# override=True 是关键: shell 里常设了 OPENAI_API_KEY / OPENAI_BASE_URL
# (例如指向 minimax 公开 API), dotenv 默认不覆盖, 会导致 .env 不生效.
# 想要 cli-sample 用 Tong-Agent 的内网 LLM, 必须 override=True.
from dotenv import load_dotenv  # noqa: E402

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)


# ============================================================
# TongAgent SDK imports
# ============================================================
# Agent base class (只起文档作用, 我们不用它的抽象方法).
from tongagents.agent import Agent, AgentSettings  # noqa: E402

# StatelessReactAgent: SDK 真正的同步单步 Agent. step(input_event) → list[Action]
# 内部: LLM 调用 + function calling + 工具调度 + 多轮 tool 循环 全自动.
from tongagents.agents.llm_agent import StatelessReactAgent, ReactAgentSetting  # noqa: E402
from tongagents.agents.llm import ModelConfig, ModelProvider  # noqa: E402
from tongagents.agents.llm_agent.defs import LLMInputEvent  # noqa: E402
from tongagents.agents.llm.messages import UserPromptMessage  # noqa: E402

# SDK 默认工具注册 (11 个工具)
from tongagents_cli.default_agent.tools import register_default_tools  # noqa: E402
from tongagents.tools.tool_manager import ToolManager  # noqa: E402


# ============================================================
# 注册 SDK 默认工具 + 构造 StatelessReactAgent
# ============================================================
# 必须在构造 Agent 之前调用, 把 11 个工具注册到 SDK 内部 ToolManager.
register_default_tools()

# SDK 读 env 自己填 (OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL 都在 env 里).
_llm_config = ModelConfig(model_provider=ModelProvider.OPENAI_COMPATIBLE)

# 极简 system prompt — SDK 默认 prompt 太啰嗦, cli-sample 要直接答问题 + 调工具.
_SYSTEM_PROMPT = (
    "你是 cli-sample agent, 帮用户操作本地文件 (读 / 写 / 列 / 搜). "
    "普通问题直接答, 文件操作必须调工具. 用中文回答."
)

_AGENT_SETTINGS = ReactAgentSetting(
    name="cli-sample-agent",
    llm_config=_llm_config,
    tool_identifier_list=list(ToolManager.tool_classes.keys()),
    system_prompt=_SYSTEM_PROMPT,
)


# ============================================================
# AgentSettings: 保留, 只起文档作用.
# ============================================================
SETTINGS = AgentSettings(
    name="cli-sample-agent",
    description="最简 CLI 样例 Agent, 用 SDK StatelessReactAgent + 默认 11 工具",
    capabilities=["chat", "file-ops"],
    model=os.getenv("OPENAI_MODEL", "gpt-4"),
    temperature=0.7,
    max_iterations=10,
    verbose=False,
    topic="cli-sample",
)


# ============================================================
# Agent 子类: 薄壳包 StatelessReactAgent.step()
# ============================================================
class CliSampleAgent(Agent):
    """最简 CLI Agent, 内部用 SDK 的 StatelessReactAgent 跑 LLM.

    step() 包装 SDK 的 StatelessReactAgent.step() — SDK 自己负责:
      - LLM 调用 (OpenAI 兼容 API, 从 env 读 OPENAI_*)
      - function calling 解析
      - 工具分发 + 结果回填
      - 多轮 tool 循环

    我们只做:
      - REPL 输入解析
      - LLMInputEvent 包装
      - 返回 list 里取最终回复 TextAction.content
    """

    agent_setting = SETTINGS

    def __init__(self):
        super().__init__(agent_setting=SETTINGS)
        # StatelessReactAgent 不持久化 memory — 每次 step 都是 stateless 单轮对话.
        # (教学极简版, 不做 session 持久化)
        self._agent = StatelessReactAgent(agent_settings=_AGENT_SETTINGS)

    def step(self, event: Any) -> str:
        """处理单条 query, 调 SDK agent.step() 同步单步 → 返回最终文本.

        StatelessReactAgent.step(LLMInputEvent(input=[UserPromptMessage(q)]))
        返回 list[Action], 通常是 1 个 is_final_response=True 的 TextAction.
        """
        wrap = LLMInputEvent(input=[UserPromptMessage(str(event))])
        actions = self._agent.step(wrap)
        # 找 is_final_response=True 的 TextAction, 它的 content 是最终回复
        for action in actions:
            if getattr(action, "is_final_response", False):
                return (action.content or "").strip()
        # fallback: 第一个有 content 的 TextAction
        for action in actions:
            if hasattr(action, "content") and action.content:
                return action.content.strip()
        return ""

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
  cli-sample: TongAgents CLI 极简样例 (走 SDK)
============================================================
  Agent: StatelessReactAgent (SDK default)
  工具: {tool_count} 个 (bash / write / read / edit / glob / grep / ...)
  模型: {model}
  端点: {base_url}
============================================================
""".strip()


def main() -> None:
    """REPL 主循环."""
    model = os.environ.get("OPENAI_MODEL", "(unset)")
    base_url = os.environ.get("OPENAI_BASE_URL", "(default)")
    tool_count = len(ToolManager.tool_classes)
    print(BANNER.format(tool_count=tool_count, model=model, base_url=base_url))

    agent = CliSampleAgent()

    try:
        while True:
            try:
                query = input(">>> ").strip()
            except EOFError:
                # Ctrl+D / stdin 关闭
                print()
                break

            if not query:
                continue
            if query.lower() in ("exit", "quit", "q"):
                break

            # 调 Agent: SDK agent.step() 同步单步, LLM + 工具调度全自动
            try:
                response = agent.step(query)
                print(f"  {response}")
            except Exception as e:  # noqa: BLE001
                print(f"  [error] {type(e).__name__}: {e}")
            print()
    except KeyboardInterrupt:
        print("\n[interrupted]")

    print("bye!")


if __name__ == "__main__":
    main()