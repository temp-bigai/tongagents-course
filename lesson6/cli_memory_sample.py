#!/usr/bin/env python3
"""
cli_memory_sample: Lesson 6 — 给论文综述 Agent 装上持久化记忆

在 Lesson 5 (search_arxiv + StatelessReactAgent) 基础上:
- Agent: StatelessReactAgent -> ReActAgentWithMemory (SDK 自带, 换类即可)
- Memory: 学生实现的 FileMemory (memory/file_memory.py), JSONL 落盘
- 接线:  LLMRunContext(memory=FileMemory(...)) 从构造参数注入

预期演示 (跨进程记忆):
    第 1 次运行:  >>> 检索 LLM Agent memory 相关论文，并生成中文综述
                  (调用 search_arxiv -> 输出综述 -> 写入 paper_memory.jsonl)  exit
    第 2 次运行:  >>> 上一篇综述提到的方法分类，再展开讲讲
                  (不调 search_arxiv, 基于记忆里的上一篇综述回答)

用法 (lesson6 自己的环境, 见 README 第 0 步; 仍复用 ../cli-sample 的 tools 与 .env):
    cd lesson6 && python cli_memory_sample.py
"""
from __future__ import annotations

import importlib.metadata
import os
import sys
from pathlib import Path

# ------------------------------------------------------------
# sys.path: lesson6/ (memory 包) + ../cli-sample (tools 包)
# ------------------------------------------------------------
_LESSON6_DIR = Path(__file__).resolve().parent
_CLI_SAMPLE_DIR = _LESSON6_DIR.parent / "cli-sample"
for _p in (str(_LESSON6_DIR), str(_CLI_SAMPLE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# 同 cli_sample.py: 规避 mcp 包 metadata 探测问题
_orig_version = importlib.metadata.version


def _safe_version(name: str) -> str:
    try:
        return _orig_version(name)
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


importlib.metadata.version = _safe_version

# .env 加载 (同 cli_sample.py, 必须在 SDK import 之前)
from dotenv import load_dotenv  # noqa: E402

for _env in (_CLI_SAMPLE_DIR / ".env", _LESSON6_DIR / ".env"):
    if _env.exists():
        load_dotenv(_env, override=True)
        break

# ------------------------------------------------------------
# TongAgent SDK imports
# ------------------------------------------------------------
from tongagents.agents.llm import ModelConfig, ModelProvider  # noqa: E402
from tongagents.agents.llm_agent import (  # noqa: E402
    LLMRunContext,
    ReactAgentSetting,
)
from tongagents.agents.llm_agent.react_agent_with_memory import (  # noqa: E402
    ReActAgentWithMemory,
)
from tongagents.agents.context_window.base import ChatHistoryUnit  # noqa: E402
from tongagents.tools.tool_manager import ToolManager  # noqa: E402

# Lesson 5 的本地工具 (search_arxiv 在 Lesson 5 已注册进 tools/__init__.py)
from tools import register_default_tools  # noqa: E402

# Lesson 6 学生实现
from memory import FileMemory  # noqa: E402

# ============================================================
# 记忆配置: 文件路径 + 会话标识 (重启后三者一致才能恢复)
# ============================================================
MEMORY_FILE = _LESSON6_DIR / "paper_memory.jsonl"
AGENT_ID = "paper-agent"
SESSION_ID = "paper-review"


def build_memory() -> FileMemory:
    """TODO(4): 构造你的 FileMemory 实例.

    提示: 用上面的 MEMORY_FILE / AGENT_ID / SESSION_ID 三个常量,
    返回 FileMemory(...). 一行即可.
    """
    # TODO(4): 删除下面这行, 返回 FileMemory 实例
    raise NotImplementedError("Lesson 6 TODO(4): 实现 build_memory")


# ============================================================
# System Prompt: 在 Lesson 5 综述规则之上增加多轮记忆规则
# ============================================================
_SYSTEM_PROMPT = (
    "你是论文综述 agent。收到论文综述请求后，必须先调用 search_arxiv 检索，"
    "再基于工具返回的论文元数据和摘要用中文 Markdown 输出综述，并声明证据边界。"
    # ---- TODO(5): 多轮记忆规则 (至少补两条) ----
    # 1. 上下文中已有上一轮综述时, 相关问题直接引用它回答, 不要重复检索;
    # 2. 回答需注明依据来源: "上一轮综述" 还是 "本轮新检索";
    # 3. 只有当用户要求新方向/新时间范围的论文时才再次调用 search_arxiv。
)


# ============================================================
# Agent: 薄壳包 ReActAgentWithMemory.step()
# ============================================================
class CliMemoryAgent:
    """带持久化记忆的 CLI Agent.

    与 Lesson 5 的区别只有两处:
    - dep_context = LLMRunContext(memory=...)  # 注入记忆 (TODO(6))
    - StatelessReactAgent -> ReActAgentWithMemory
    其余 (REPL / 工具 / 返回值提取) 与 Lesson 5 完全一致.
    """

    def __init__(self):
        memory = build_memory()  # TODO(4) 完成后即为 FileMemory 实例
        # TODO(6): 构造 dep_context 并传给下面的 agent.
        # 提示: dep_context = LLMRunContext(memory=memory)
        #       注意 dep_context 不能是 None (agent 内部直接读 .memory)
        dep_context = None  # <- 改掉这一行
        self._agent = ReActAgentWithMemory(
            dep_context=dep_context,
            agent_settings=ReactAgentSetting(
                name="lesson6-memory-agent",
                llm_config=ModelConfig(model_provider=ModelProvider.OPENAI_COMPATIBLE),
                tool_identifier_list=["search_arxiv"],
                system_prompt=_SYSTEM_PROMPT,
                tool_call_memory=False,  # 综述进上下文即可, arXiv 原始结果不进
                max_history_len=5,       # 滑窗: 最多带最近 5 轮对话
            ),
        )


# ============================================================
# step() 包装: 与 cli_sample.py 相同的返回值提取逻辑
# ============================================================
def agent_step(agent: ReActAgentWithMemory, query: str) -> str:
    """调 agent.step(query), 从返回的 Action 列表里提取最终文本.

    注意: ReActAgentWithMemory.step() 直接接受字符串
    (它的 belief_update 会把 str 包装成 RAGQuery).
    """
    actions = agent.step(query)
    for action in actions:
        if getattr(action, "is_final_response", False):
            return (action.content or "").strip()
    for action in actions:
        if hasattr(action, "content") and action.content:
            return action.content.strip()
    return ""


# ============================================================
# REPL 入口
# ============================================================
BANNER = """
============================================================
  lesson6: 论文综述 Agent + FileMemory 持久化记忆
============================================================
  Agent:   ReActAgentWithMemory (SDK)
  Memory:  {memory_file}
  Session: {agent_id} / {session_id}
  恢复:    启动时从记忆文件恢复最近 {n} 轮对话
  模型:    {model}
============================================================
  演示跨进程记忆:
    第 1 次运行: 检索 LLM Agent memory 相关论文，并生成中文综述
    exit 退出后重新运行, 再问: 上一篇综述的方法分类再展开讲讲
============================================================
""".strip()


def restored_unit_count(memory: FileMemory) -> int:
    """启动时数一数记忆里有几轮对话 — 顺便自检你的 FileMemory."""
    msgs = memory.get_messages(
        recent_n=5, config={ChatHistoryUnit.__name__: ChatHistoryUnit.load}
    )
    return len(msgs)


def main() -> None:
    register_default_tools()

    if "search_arxiv" not in ToolManager.tool_classes:
        print("[提示] 未找到 search_arxiv 工具 — 请先完成 Lesson 5,")
        print("       并把 ArxivSearchTool 加入 cli-sample/tools/__init__.py")
        sys.exit(1)

    try:
        memory = build_memory()
    except NotImplementedError as e:
        print(f"[提示] 先完成 TODO(4): {e}")
        sys.exit(1)

    model = os.environ.get("OPENAI_MODEL", "(unset)")
    restored = restored_unit_count(memory)
    print(
        BANNER.format(
            memory_file=MEMORY_FILE,
            agent_id=AGENT_ID,
            session_id=SESSION_ID,
            n=restored,
            model=model,
        )
    )
    if restored:
        print(f"  [记忆] 已恢复 {restored} 轮对话 (来自 {MEMORY_FILE.name})\n")

    cli = CliMemoryAgent()

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
                response = agent_step(cli._agent, query)
                print(f"  {response}")
            except Exception as e:  # noqa: BLE001
                print(f"  [error] {type(e).__name__}: {e}")
            print()
    except KeyboardInterrupt:
        print("\n[interrupted]")

    print("bye! (对话已写入记忆文件, 重启后可继续)")


if __name__ == "__main__":
    main()
