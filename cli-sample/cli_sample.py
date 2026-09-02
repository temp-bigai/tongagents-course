#!/usr/bin/env python3
"""
cli-sample: 最简 TongAgents CLI 样例

仿造 Tong-Agent 的 CLI, 但极简化:
- 单文件 REPL 循环 (Read-Eval-Print)
- 调用基于 tongagents SDK 的 Agent
- Agent 内置 3 个 OS 工具 (list_dir / read_file / write_file)
- 输入 'exit' / 'quit' / Ctrl+D 退出

用法:
    $ python cli_sample.py

环境变量:
    OPENAI_API_KEY: tongagents Agent 用的 LLM key (从 .env 读)
    OPENAI_BASE_URL: (可选) OpenAI 兼容端点
    OPENAI_MODEL: (可选) 模型名
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

# 先 load .env (在所有 SDK import 之前)
from dotenv import load_dotenv  # noqa: E402

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# 现在才 import SDK
from tongagents.agent import Agent, AgentSettings  # noqa: E402


# ============================================================
# AgentSettings: 配置 Agent 行为
# ============================================================
SETTINGS = AgentSettings(
    name="cli-sample-agent",
    description="最简 CLI 样例 Agent, 可以读 / 写 / 列文件, 回答用户问题",
    capabilities=["file-ops", "chat"],
    model=os.getenv("OPENAI_MODEL", "gpt-4"),
    temperature=0.0,
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
        # 自动建父目录
        parent = Path(path).parent
        if str(parent) and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"
    return f"written: {path} ({len(content)} chars)"


# 工具清单 (供 Agent 内部使用, 也可暴露给 LLM 做 tool calling)
TOOLS: dict[str, Any] = {
    "list_dir": list_dir,
    "read_file": read_file,
    "write_file": write_file,
}


# ============================================================
# Agent 子类: 演示如何把工具注册到 Agent
# ============================================================
class CliSampleAgent(Agent):
    """最简 CLI Agent, 内置 3 个 OS 工具.

    本样例不调真实 LLM (避免 SDK 1.6GB 依赖 + API key), 而是
    用关键词路由把用户 query 派发到对应工具, 让 REPL 能跑通.

    想换成真实 LLM + tool calling 时, 把 step() 里的路由逻辑替换成
    OpenAI / 兼容 SDK 的 chat completion 调用, 并把 TOOLS 转成
    OpenAI function calling schema 即可.
    """

    agent_setting = SETTINGS

    def __init__(self):
        super().__init__(agent_setting=SETTINGS)
        self.tools = TOOLS

    # ---------------------- 路由逻辑 (极简) ----------------------
    def _route(self, query: str) -> str:
        """把 query 派发到 list_dir / read_file / write_file / 默认 echo."""
        q = query.strip()
        lower = q.lower()

        # 写文件: write <path> with content "..."
        if lower.startswith("write ") and " with content " in lower:
            try:
                head, tail = lower.split(" with content ", 1)
                path = head[len("write "):].strip().strip('"').strip("'")
                # 提取引号内 content (支持 " 或 ')
                if tail.startswith('"') and tail.endswith('"'):
                    content = tail[1:-1]
                elif tail.startswith("'") and tail.endswith("'"):
                    content = tail[1:-1]
                else:
                    content = tail
                return self.tools["write_file"](path, content)
            except Exception as e:  # noqa: BLE001
                return f"error: parse write failed: {e}"

        # 读文件: read <path>
        if lower.startswith("read "):
            path = q[len("read "):].strip().strip('"').strip("'")
            return self.tools["read_file"](path)

        # 列目录: list [path] / ls [path]
        if lower.startswith("list") or lower.startswith("ls"):
            tokens = q.split()
            path = tokens[1] if len(tokens) >= 2 else "."
            return self.tools["list_dir"](path)

        # 默认 echo (让 REPL 能跑通)
        return f"[echo] {q}"

    # ---------------------- Agent 抽象方法 ----------------------
    def step(self, event: Any) -> str:
        """处理单条事件, 返回字符串回复."""
        return self._route(str(event))

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
  cli-sample: TongAgents CLI 极简样例
============================================================
  输入问题, 按回车. 输入 'exit' / 'quit' / 'q' / Ctrl+D 退出.
  内置工具 (路由关键词):
    list [path]   列出目录 (默认当前目录)
    read <path>   读文件 (前 200 行)
    write <path> with content "..."   写文件
  默认: echo 回显
============================================================
""".strip()


def main() -> None:
    """REPL 主循环."""
    print(BANNER)

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

            # 调 Agent (流式: 即使本样例只 yield 一次, 也演示 SDK 调用方式)
            try:
                for response in agent.run(iter([query])):
                    print(f"  {response}")
            except Exception as e:  # noqa: BLE001
                print(f"  [error] {type(e).__name__}: {e}")
            print()
    except KeyboardInterrupt:
        print("\n[interrupted]")

    print("bye!")


if __name__ == "__main__":
    main()
