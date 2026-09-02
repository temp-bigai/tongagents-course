#!/usr/bin/env python3
"""
cli-sample: 最简 TongAgents CLI 样例 (接真实 LLM)

仿造 Tong-Agent 的 CLI, 但极简化:
- 单文件 REPL 循环 (Read-Eval-Print)
- 调用基于 tongagents SDK 的 Agent
- Agent.step() 接真实 LLM (OpenAI 兼容 API, function calling)
- 内置 3 个 OS 工具 (list_dir / read_file / write_file)
- 输入 'exit' / 'quit' / Ctrl+D 退出

用法:
    # 1. 复制 Tong-Agent .env (含 OPENAI_* 三件套)
    cp ~/work/codework/tong_agents/Tong-Agent/.env .env

    # 2. 装 openai (>=1.0)
    pip install openai

    # 3. 跑
    $ python cli_sample.py

环境变量 (从 .env 读, override=True 覆盖 shell env):
    OPENAI_API_KEY:   LLM key
    OPENAI_BASE_URL:  OpenAI 兼容端点 (默认 https://api.openai.com/v1)
    OPENAI_MODEL:     模型名 (默认 gpt-4)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

# ============================================================
# .env 加载 (必须在 SDK / openai import 之前)
# ============================================================
# override=True 是关键: shell 里常设了 OPENAI_API_KEY / OPENAI_BASE_URL
# (例如指向 minimax 公开 API), dotenv 默认不覆盖, 会导致 .env 不生效.
# 想要 cli-sample 用 Tong-Agent 的内网 LLM, 必须 override=True.
from dotenv import load_dotenv  # noqa: E402

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

# SDK import
from tongagents.agent import Agent, AgentSettings  # noqa: E402

# openai SDK (>=1.0)
import openai  # noqa: E402


# ============================================================
# AgentSettings: 配置 Agent 行为
# ============================================================
SETTINGS = AgentSettings(
    name="cli-sample-agent",
    description="最简 CLI 样例 Agent, 可以读 / 写 / 列文件, 回答用户问题",
    capabilities=["file-ops", "chat"],
    model=os.getenv("OPENAI_MODEL", "gpt-4"),
    temperature=0.7,
    max_iterations=5,
    verbose=False,
    topic="cli-sample",
)


# ============================================================
# 工具: OS 文件操作 (用户问"看 / 写" 时用)
# ============================================================
def list_dir(path: str = ".") -> str:
    """列出目录内容. 返回 '\\n' 分隔的文件名列表."""
    try:
        entries = sorted(os.listdir(path))
        return "\n".join(entries)
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"


def read_file(path: str, max_lines: int = 200) -> str:
    """读文件内容, 返回字符串. 最多 max_lines 行, 超出截断并提示."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return f"error: file not found: {path}"
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"

    lines = content.splitlines()
    if len(lines) > max_lines:
        truncated = "\n".join(lines[:max_lines])
        return f"{truncated}\n... (truncated, total {len(lines)} lines)"
    return content


def write_file(path: str, content: str) -> str:
    """写文件. 返回 'written: <path> (<n> chars)'."""
    try:
        parent = Path(path).parent
        if str(parent) and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"
    return f"written: {path} ({len(content)} chars)"


# 工具实现 map (function name -> callable)
TOOL_IMPLS: dict[str, Any] = {
    "list_dir": list_dir,
    "read_file": read_file,
    "write_file": write_file,
}

# 工具定义 (OpenAI function calling 格式)
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出目录的文件名. 路径不存在或无权限时返回错误.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径, 默认 '.' (当前目录)",
                        "default": ".",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读文件全部内容. 大文件自动截断到 max_lines 行.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读的文件路径",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "最多返回多少行, 默认 200",
                        "default": 200,
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "把 content 写到 path. 自动建父目录.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目标文件路径",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整内容",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
]


# ============================================================
# LLM 调用 (OpenAI 兼容 API + function calling)
# ============================================================
SYSTEM_PROMPT = (
    "你是 cli-sample agent, 帮用户在命令行里操作本地文件. "
    "可用工具: list_dir (列目录) / read_file (读文件) / write_file (写文件). "
    "普通问题直接答, 文件操作必须调工具. 用中文回答."
)


def _make_client() -> openai.OpenAI:
    """从 env 构造 OpenAI 客户端 (兼容任意 OPENAI_BASE_URL)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")  # 可选, 不传走默认
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY 未设置. 请 cp ~/work/codework/tong_agents/Tong-Agent/.env .env "
            "或在环境变量 / .env 里填 OPENAI_API_KEY."
        )
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return openai.OpenAI(**kwargs)


def _call_llm(user_message: str, max_tool_rounds: int = 3) -> str:
    """单轮 chat, 最多 max_tool_rounds 轮 tool 调用循环.

    简化: 每轮最多 1 个 tool call (实际 SDK 可并发), 教学清晰.
    """
    client = _make_client()
    model = os.environ.get("OPENAI_MODEL", "gpt-4")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    for _round in range(max_tool_rounds + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )
        msg = response.choices[0].message

        # 没 tool call → 直接返回 content
        if not msg.tool_calls:
            return msg.content or ""

        # 处理 tool calls (一轮可能有多个, 这里按顺序串行)
        messages.append(msg)  # type: ignore[arg-type]
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}
            impl = TOOL_IMPLS.get(fn_name)
            if impl is None:
                result = f"error: unknown tool '{fn_name}'"
            else:
                try:
                    result = impl(**fn_args)
                except Exception as e:  # noqa: BLE001
                    result = f"error: {type(e).__name__}: {e}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )

    # 超过 max_tool_rounds
    return "(max tool iterations reached, 没有最终回答)"


# ============================================================
# Agent 子类
# ============================================================
class CliSampleAgent(Agent):
    """最简 CLI Agent, 继承 tongagents.agent.Agent, step() 调真实 LLM."""

    agent_setting = SETTINGS

    def __init__(self):
        super().__init__(agent_setting=SETTINGS)

    def step(self, event: Any) -> str:
        """处理单条事件, 调真实 LLM (含 function calling 循环)."""
        return _call_llm(str(event))

    def run(self, events: Iterator[Any]) -> Iterator[str]:
        """流式处理事件, 每条产生一个回复."""
        for event in events:
            yield self.step(event)

    async def astep(self, event: Any) -> str:
        """异步单步处理."""
        return self.step(event)

    async def arun(self, events: AsyncIterator[Any] | Any) -> AsyncIterator[str]:
        """异步流式处理."""
        if hasattr(events, "__aiter__"):
            async for event in events:
                yield await self.astep(event)
        else:
            for event in events:
                yield await self.astep(event)


# ============================================================
# REPL 入口
# ============================================================
BANNER = """
============================================================
  cli-sample: TongAgents CLI 极简样例 (LLM 真实调用)
============================================================
  输入问题, 按回车. 输入 'exit' / 'quit' / 'q' / Ctrl+D 退出.
  内置工具 (LLM 自动选择):
    list_dir(path=".")    列出目录
    read_file(path, ...)  读文件 (前 200 行)
    write_file(path, ...) 写文件
  模型: {model}    端点: {base_url}
============================================================
""".strip()


def main() -> None:
    """REPL 主循环."""
    model = os.environ.get("OPENAI_MODEL", "gpt-4")
    base_url = os.environ.get("OPENAI_BASE_URL", "(default)")
    print(BANNER.format(model=model, base_url=base_url))

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

            # 调 Agent (单条 query → 一次 step → 真实 LLM + 工具循环)
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
