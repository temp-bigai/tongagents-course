#!/usr/bin/env python3
"""CLI Sample with EventSource - v5 (Task #3472).

v5 关键改动 (相对 v4):
- **统一 input_queue**: EventSourceRuntime 内部持有 input_queue (user + event 一个源)
- **handler 主动推**: AgentHandler.handle(event, runtime) 把 event 包装推 runtime.input_queue
- **stdin reader 后台线程**: stdin -> runtime.add_user_input()
- **main loop 单源**: runtime.get_input() 阻塞拿 input (不区分 user/event)
- **无 es_dispatcher 线程**: v4 那个独立线程被消除, handler 自己负责包装+推

工作流:
    ┌─────────────────────────────────────────────────────────────────┐
    │ stdin reader (后台线程)                                           │
    │   line = input('> ')                                             │
    │   runtime.add_user_input(line, source_tag='stdin')               │
    └─────────────────────────────────────────────────────────────────┘
                                  ↓
    ┌─────────────────────────────────────────────────────────────────┐
    │ TimerEventSource (后台线程)                                      │
    │   every 5s: runtime.add_event(event)                             │
    │     -> AgentHandler.handle(event, runtime)                       │
    │     -> runtime.add_user_input(wrapped, source_tag='es_event:...')│
    └─────────────────────────────────────────────────────────────────┘
                                  ↓
    ┌─────────────────────────────────────────────────────────────────┐
    │ runtime.input_queue (统一: user + event)                         │
    │   item = {'origin': 'stdin'/'es_event:...', 'content': str, ...} │
    └─────────────────────────────────────────────────────────────────┘
                                  ↓
    ┌─────────────────────────────────────────────────────────────────┐
    │ main loop (主线程)                                               │
    │   item = runtime.get_input(timeout=0.5)                          │
    │   agent.step([UserPromptMessage(item['content'])])               │
    │   print(response)                                                │
    └─────────────────────────────────────────────────────────────────┘

复用 vs 新增:
- 复用 (来自 cli-sample/cli_sample.py):
    * agent 构造 (StatelessReactAgent + 6 tools, 通过 AgentHandler 提供)
    * REPL 循环结构 (input -> step -> print)
    * input 命令解析 (exit/quit/q 退出, 空输入跳过)
- 新增 (本文件):
    * stdin_reader 后台线程: 把 stdin 推到 runtime.input_queue (统一来源)
    * main loop 单源从 runtime.input_queue 取 (不再独立读 stdin)
    * Runtime 持有统一 input_queue (user + event 一个 queue)

设计要点 (v4 -> v5):
- v4: runtime 用 auto_dispatch=False, 内部 _queue 存 Event;
     es_dispatcher 线程独立把 Event 转 user input 推 input_queue;
     main loop 从 input_queue 拿 (但 stdin 不入 input_queue, 设计割裂).
- v5: runtime 拥有统一 input_queue (user + event 一个);
     handler.handle(event, runtime) 把 event 包装推 runtime.input_queue;
     stdin_reader 后台线程也调 runtime.add_user_input();
     main loop 单源 runtime.get_input(), 不再区分 user/event.

用法::

    cd cli-sample-with-event-soource/src
    python3 main.py
    # 输入 'exit' / 'quit' / 'q' 退出; 也可以 Ctrl+D / Ctrl+C

环境变量:
    EVENT_INTERVAL_SECONDS: 定时间隔 (默认 30)
    EVENT_MAX_COUNT: 最大触发次数 (默认 5, 触发完后等 user 输入; 不会自动退出)
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

# 让脚本能找到本地 event_source/handlers 包
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from event_source import EventSourceRuntime, TimerEventSource  # noqa: E402
from handlers import AgentHandler  # noqa: E402


# ============================================================================
# 日志配置
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli-sample-with-event-soource")


# ============================================================================
# 配置 (环境变量覆盖)
# ============================================================================
INTERVAL_SECONDS = float(os.getenv("EVENT_INTERVAL_SECONDS", "30"))
MAX_COUNT = int(os.getenv("EVENT_MAX_COUNT", "5"))


# ============================================================================
# stdin reader: 后台线程, 把 stdin 推到 runtime.input_queue
# ============================================================================
def stdin_reader_loop(runtime: EventSourceRuntime, prompt: str = "> ") -> None:
    """后台线程: 读 stdin, 每行作为 user input 推到 runtime.input_queue.

    v5 改动: 不再是 main loop 直接 input(), 而是后台线程读 stdin 后
    推 runtime.add_user_input(). 这样 main loop 只从 runtime.get_input()
    拿 input, 不需要再关心 stdin / select 等 IO 多路复用.
    """
    logger.info("[stdin_reader] 启动, prompt=%r", prompt)
    while runtime.is_running:
        try:
            line = input(prompt)
            stripped = line.strip()
            if not stripped:
                continue
            # 退出命令: 推一个特殊 user input 让 main loop 退出
            if stripped.lower() in ("exit", "quit", "q"):
                runtime.add_user_input("__exit__", source_tag="stdin")
                runtime.stop()  # 同时停 runtime, 让 main loop 退出
                break
            runtime.add_user_input(stripped, source_tag="stdin")
        except EOFError:
            logger.info("[stdin_reader] stdin EOF, 退出")
            runtime.add_user_input("__exit__", source_tag="stdin")
            runtime.stop()
            break
        except KeyboardInterrupt:
            logger.info("[stdin_reader] Ctrl+C, 退出")
            runtime.add_user_input("__exit__", source_tag="stdin")
            runtime.stop()
            break
        except Exception as e:
            logger.exception("[stdin_reader] 异常: %s", e)
            # 避免线程死循环, 短暂 sleep
            time.sleep(0.1)

    logger.info("[stdin_reader] 退出")


# ============================================================================
# 核心 REPL 循环: 复用 cli-sample 模式, 但单源 runtime.get_input()
# ============================================================================
def run_cli_loop(runtime: EventSourceRuntime) -> None:
    """复用 cli-sample 的 REPL 循环, 但 input **单一来源** 是 runtime.input_queue.

    对比 cli-sample/cli_sample.py:main():
        query = input(">>> ").strip()
        if not query: continue
        if query in ("exit", "quit", "q"): break
        response = agent.step(query)
        print(f"  {response}")

    v5 等价结构:
        item = runtime.get_input(timeout=0.5)     # 单源 (user + event 都来自这里)
        content = item['content']
        origin = item['origin']
        if content == '__exit__': break
        response = agent_handler.agent.step(LLMInputEvent(input=[UserPromptMessage(content)]))
        print(response)

    关键点:
    - main loop 不直接调 input() (避免跟 stdin_reader 抢)
    - 不再区分 user input vs ES event (走同一条 agent.step 路径)
    - 用 '__exit__' sentinel 让 stdin_reader 通知 main loop 退出
    """
    logger.info("=" * 60)
    logger.info("CLI Sample with EventSource (v5) — 统一 input_queue")
    logger.info("  输入 'exit' / 'quit' / 'q' 退出")
    logger.info("  stdin + ES event 走同一个 runtime.input_queue")
    logger.info("=" * 60)

    # SDK imports (跟 cli-sample 一样)
    from tongagents.agents.llm_agent.defs import LLMInputEvent  # type: ignore
    from tongagents.agents.llm.messages import UserPromptMessage  # type: ignore

    # 拿 agent (从已注册的 handler 里)
    if not runtime._handlers:
        logger.error("[main] 没有注册 handler, 退出")
        return
    agent_handler = runtime._handlers[0]
    agent = agent_handler.agent

    try:
        while runtime.is_running:
            item = runtime.get_input(timeout=0.5)
            if item is None:
                continue
            content = item["content"]
            origin = item["origin"]
            logger.info(
                "[main] 处理输入 (origin=%s, queue_size=%d): %s",
                origin,
                runtime.input_queue.qsize(),
                content[:120].replace("\n", " | "),
            )

            # 退出 sentinel
            if content == "__exit__":
                logger.info("[main] 收到退出信号, bye!")
                break

            # 复用 cli-sample 模式: agent.step() 同步单步, SDK 自己跑 LLM + tool 循环
            try:
                wrap = LLMInputEvent(input=[UserPromptMessage(content)])
                actions = agent.step(wrap)
                # 跟 cli-sample 一致: 找 is_final_response=True 的 TextAction
                response = ""
                for action in actions:
                    if getattr(action, "is_final_response", False):
                        response = (action.content or "").strip()
                        break
                if not response:
                    # fallback: 第一个有 content 的
                    for action in actions:
                        if hasattr(action, "content") and action.content:
                            response = action.content.strip()
                            break
                logger.info(
                    "[agent] (origin=%s) %s", origin,
                    response if response else "(空响应)",
                )
                print(response)
            except Exception as e:  # noqa: BLE001
                logger.exception("[main] agent.step 失败: %s", e)
                print(f"  [error] {type(e).__name__}: {e}")

    except KeyboardInterrupt:
        logger.info("[main] Ctrl+C, 退出")

    # 退出时停 runtime (ES source 不再触发新 event)
    if runtime.is_running:
        runtime.stop()
    logger.info("=" * 60)
    logger.info("CLI Sample (v5) 退出")
    logger.info("=" * 60)


# ============================================================================
# main 入口
# ============================================================================
def main() -> int:
    logger.info("=" * 60)
    logger.info("CLI Sample with EventSource + Agent 启动 (Task #3472 v5)")
    logger.info("  interval = %.1f 秒", INTERVAL_SECONDS)
    logger.info("  max_count = %d", MAX_COUNT)
    logger.info("  设计: 统一 input_queue (user + event)")
    logger.info("    - Runtime.input_queue 持有统一 queue")
    logger.info("    - stdin_reader 后台线程 -> runtime.add_user_input()")
    logger.info("    - handler.handle(event, runtime) -> runtime.add_user_input()")
    logger.info("    - main loop 单源 runtime.get_input()")
    logger.info("=" * 60)

    # 1. 构造 runtime (v5: 不需要 auto_dispatch 参数, 简化为单 queue)
    runtime = EventSourceRuntime()

    # 2. 构造 handler + source
    agent_handler = AgentHandler(name="cli_es_sample_agent")
    timer_es = TimerEventSource(
        name="sample_timer",
        interval_seconds=INTERVAL_SECONDS,
        max_count=MAX_COUNT,
        event_type="timer.tick",
        payload={"source": "sample"},
    )

    # 3. 注册 + 绑定
    runtime.add_source(timer_es)
    runtime.add_handler(agent_handler)
    runtime.bind(timer_es, agent_handler)

    # 4. 启动 source (TimerEventSource 后台线程跑)
    runtime.start()

    # 5. stdin reader 后台线程: 把 stdin 推到 runtime.input_queue
    reader = threading.Thread(
        target=stdin_reader_loop,
        args=(runtime, "> "),
        name="stdin-reader",
        daemon=True,
    )
    reader.start()

    # 6. 主循环: 单源 runtime.get_input()
    try:
        run_cli_loop(runtime)
    finally:
        # 清理
        if runtime.is_running:
            runtime.stop()
        reader.join(timeout=2.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())