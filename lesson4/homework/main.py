#!/usr/bin/env python3
"""main — REPL 入口 (已给, 不需要修改).

python main.py 启动后:
    >>> 在 /tmp/demo 下创建 hello.txt, 内容为 "hello lesson4"
    （观察: [turn 1] 🔧 write_file(...) → 模型自己选工具, 你的循环去执行）
    >>> exit
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HOMEWORK_DIR = Path(__file__).resolve().parent
if str(_HOMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(_HOMEWORK_DIR))

# .env 必须在导入 mycli 之前加载 (llm.py 在 import 时读 OPENAI_MODEL)
from dotenv import load_dotenv  # noqa: E402

_env_path = _HOMEWORK_DIR / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)  # override=True: .env 优先于 shell 环境变量

from mycli import tools  # noqa: E402,F401  # import 即完成 6 个工具注册 (tools.py 底部的 register 调用)
from mycli.agent import agent_loop  # noqa: E402
from mycli.registry import TOOL_REGISTRY  # noqa: E402

_SYSTEM_PROMPT = (
    "你是本地文件操作 agent, 帮用户读写、编辑、搜索本地文件, 也可执行 shell 命令. "
    "普通问题直接回答; 文件/命令操作必须调用工具, 拿到工具结果后再回答. 用中文回答."
)

BANNER = """
============================================================
  lesson4 课后作业: 手写 ReAct 循环的本地文件 CLI Agent
============================================================
  模型:  {model}
  端点:  {base_url}
  工具:  {tool_count} 个 ({tool_names})
============================================================
  试试: 在 /tmp 下创建 hello.txt 并写入 hello lesson4
  退出: exit / quit / Ctrl+D
============================================================
""".strip()


def main() -> None:
    print(
        BANNER.format(
            model=os.environ.get("OPENAI_MODEL", "(unset)"),
            base_url=os.environ.get("OPENAI_BASE_URL", "(default)"),
            tool_count=len(TOOL_REGISTRY),
            tool_names=", ".join(sorted(TOOL_REGISTRY)),
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
                # verbose=True: 逐轮打印 [turn N] 🔧 工具(参数) → 结果, 看得见循环在转
                answer, _messages = agent_loop(query, system=_SYSTEM_PROMPT, verbose=True)
                print(f"  {answer}")
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
