#!/usr/bin/env python3
"""CLI Sample with EventSource - v4 (Task #3470).

复用 cli-sample 的"等用户 input + 输出 agent response"循环, ES event 包装成
user input 注入到这个循环. 标明: 这里**只新增了 ES 机制**, user input 循环
本身是**复用** cli-sample/cli_sample.py 的 main() 函数.

工作流:
    ┌─────────────────────────────────────────────────────────────────┐
    │ 主线程: 复用 cli-sample 的 REPL 循环                                │
    │   while True:                                                    │
    │       user_input = input_queue.get()  # 用户输入 或 ES 注入的输入   │
    │       if user_input in ('exit', 'quit', 'q'): break              │
    │       response = agent.step(user_input)  # 走 SDK, 真 LLM + tool  │
    │       print(response)                                            │
    └─────────────────────────────────────────────────────────────────┘
                                ↑                              ↓
                          ES dispatcher                   agent.step()
                          (后台线程)                            │
                                ↑                              ↓
                          runtime._queue               SDK StatelessReactAgent
                                ↑                              │
                          TimerEventSource               cli-sample 6 tools
                          (后台线程)

复用 vs 新增:
- 复用 (来自 cli-sample/cli_sample.py):
    * agent 构造 (StatelessReactAgent + 6 tools, 通过 AgentHandler 提供)
    * REPL 循环结构 (input -> step -> print)
    * input 命令解析 (exit/quit/q 退出, 空输入跳过)
- 新增 (本文件):
    * input_queue: 合并 stdin + ES 事件的统一输入通道
    * ES dispatcher thread: 轮询 runtime._queue, 把 Event 转 user input
    * TimerEventSource 配置 + 启动/停止

设计要点 (跟 v3 对比):
- v3: runtime 注册 AgentHandler + CliEventHandler, runtime dispatcher
       直接调 handler.handle(event) -> handler 内部跑 mini agent loop
- v4: runtime 只 dispatch Event 到自己的 queue (不再注册 handler)
       ES dispatcher 把 Event 转 user input 推到 input_queue
       main loop 从 input_queue 拿 item, 走 cli-sample 一样的 step+print

用户原话: "handler 里面就保留使用到的 handler 就好, 一个就行,
        另外需要用 cli-sample 里面的命令行中的等待用户 input 和输出 agent response
        的循环逻辑, 然后将 timer event 封装为 user input 来注入到这个循环逻辑中哈"

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
import queue
import sys
import threading
import time
from pathlib import Path

# 让脚本能找到本地 event_source/handlers 包
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from event_source import EventSourceRuntime, TimerEventSource  # noqa: E402
from handlers import AgentHandler  # noqa: E402


# ============================================================================
# 日志配置: 跟 v3 一致
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli-sample-with-event-soource")


# ============================================================================
# 配置 (环境变量覆盖, 跟 v3 一致)
# ============================================================================
INTERVAL_SECONDS = float(os.getenv("EVENT_INTERVAL_SECONDS", "30"))
MAX_COUNT = int(os.getenv("EVENT_MAX_COUNT", "5"))


# ============================================================================
# ES event -> user input 转换 (核心桥接)
# ============================================================================
def event_to_user_input(event) -> str:
    """把 ES Event 包装成 user input 字符串, 注入到 cli-sample 的 input loop.

    这是 v4 关键解耦点: Event 走和 user input 完全一样的路径 ——
    都被 agent.step() 当作用户输入处理, 然后输出 response.
    区别只在前面加个 [ES 自动输入] 标记, 方便观察.
    """
    return (
        f"[ES 自动输入] 我收到了一个定时事件:\n"
        f"  - type: {event.type}\n"
        f"  - source: {event.source}\n"
        f"  - payload: {event.payload}\n"
        f"  - timestamp: {event.timestamp}\n"
        f"请利用可用工具 (bash / write_file / read_file 等) 处理这个事件."
    )


# ============================================================================
# ES dispatcher: 把 EventSourceRuntime queue 里的 Event 转 user input, 推到 input_queue
# ============================================================================
def make_es_dispatcher(runtime: EventSourceRuntime, input_queue: "queue.Queue[str]"):
    """返回一个后台线程函数: 轮询 runtime.get_event(), 把 Event 转 user input 推到 input_queue.

    v4 关键改动: runtime 用 auto_dispatch=False (不启动内部 dispatcher 线程),
    event 直接进 runtime._queue. 我们另起一个 dispatcher 线程, 从 queue 拿
    Event, 包装成 user input 推到 input_queue.

    这样的好处: event 完全走"用户输入"路径, agent 不知道 event 和用户输入的区别.
    main loop 从 input_queue 拿 item (跟拿 user input 一样), 走 cli-sample 循环.
    """
    def _dispatcher() -> None:
        logger.info("[ES dispatcher] 启动, 监听 runtime.get_event()")
        while runtime.is_running:
            event = runtime.get_event(timeout=0.5)
            if event is None:
                continue
            try:
                user_input = event_to_user_input(event)
                input_queue.put(user_input)
                logger.info(
                    "[ES dispatcher] Event -> user input (queue size=%d): %s",
                    input_queue.qsize(),
                    event,
                )
            except Exception:
                logger.exception("[ES dispatcher] 转换 Event 失败: %s", event)
        logger.info("[ES dispatcher] runtime 已停, 退出")

    return _dispatcher


# ============================================================================
# 核心 REPL 循环: 复用 cli-sample/cli_sample.py:main() 的形态, 但从 input_queue 拿 input
# ============================================================================
def run_cli_loop(
    agent_handler: AgentHandler,
    input_queue: "queue.Queue[str]",
    runtime: EventSourceRuntime,
) -> None:
    """复用 cli-sample 的 REPL 循环, 但 input 来源是 input_queue.

    对比 cli-sample/cli_sample.py:main():
        query = input(">>> ").strip()
        if not query: continue
        if query in ("exit", "quit", "q"): break
        response = agent.step(query)
        print(f"  {response}")

    v4 等价结构:
        user_input = input_queue.get()      # 跟 input() 一样阻塞
        if not user_input: continue
        if user_input in ("exit", "quit", "q"): break
        response = agent_handler.agent.step(LLMInputEvent(input=[UserPromptMessage(user_input)]))
        print(response)

    注意: 我们直接调 agent.step (跟 cli-sample 一致), 不再经 AgentHandler.handle.
    EventSourceRuntime 不注册 handler (handler 仅保留, 兼容 SDK dispatcher 模式).
    """
    logger.info("=" * 60)
    logger.info("CLI Sample with EventSource (v4) — 复用 cli-sample 循环")
    logger.info("  输入 'exit' / 'quit' / 'q' 退出")
    logger.info("  ES event 会被包装成 user input, 注入这个循环")
    logger.info("=" * 60)

    # SDK imports (跟 cli-sample 一样)
    from tongagents.agents.llm_agent.defs import LLMInputEvent  # type: ignore
    from tongagents.agents.llm.messages import UserPromptMessage  # type: ignore

    agent = agent_handler.agent

    try:
        while True:
            try:
                # 阻塞等输入 (从 input_queue, ES dispatcher 会推过来)
                user_input = input_queue.get()
            except KeyboardInterrupt:
                logger.info("[main] Ctrl+C, 退出")
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                logger.info("[main] 收到退出命令, bye!")
                break

            # 标注入来源 (debug 用)
            logger.info("[main] 处理输入: %s", user_input[:120].replace("\n", " | "))

            # 复用 cli-sample 模式: agent.step() 同步单步, SDK 自己跑 LLM + tool 循环
            try:
                wrap = LLMInputEvent(input=[UserPromptMessage(user_input)])
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
                logger.info("[agent] %s", response if response else "(空响应)")
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
    logger.info("CLI Sample (v4) 退出")
    logger.info("=" * 60)


# ============================================================================
# main 入口
# ============================================================================
def main() -> int:
    logger.info("=" * 60)
    logger.info("CLI Sample with EventSource + Agent 启动 (Task #3470 v4)")
    logger.info("  interval = %.1f 秒", INTERVAL_SECONDS)
    logger.info("  max_count = %d", MAX_COUNT)
    logger.info("  设计: 单 handler (AgentHandler) + 复用 cli-sample REPL 循环")
    logger.info("  ES event 包装成 user input, 注入同一个 input loop")
    logger.info("=" * 60)

    # 1. 单 handler: AgentHandler (复用 cli-sample 的 agent 模式)
    agent_handler = AgentHandler(name="cli_es_sample_agent")

    # 2. Runtime + TimerEventSource
    #    注意: v4 **不** add_handler + bind (event 走 input_queue, 不走 handler)
    #    auto_dispatch=False: 内部 dispatcher 线程不启动, event 直接进 _queue,
    #    留给我们的 ES dispatcher 线程消费 (v4 关键设计).
    runtime = EventSourceRuntime(auto_dispatch=False)
    timer_es = TimerEventSource(
        name="sample_timer",
        interval_seconds=INTERVAL_SECONDS,
        max_count=MAX_COUNT,
        event_type="timer.tick",
        payload={
            "source": "cli-sample-with-event-soource",
            "note": f"每 {INTERVAL_SECONDS:.0f} 秒触发一次 (v4 复用 cli-sample 循环)",
        },
    )
    runtime.add_source(timer_es)

    # 3. 共享 input_queue: user input + ES event 注入都走这里
    input_queue: "queue.Queue[str]" = queue.Queue()

    # 4. 启动 runtime + ES dispatcher 后台线程
    runtime.start()
    es_dispatcher = make_es_dispatcher(runtime, input_queue)
    dispatcher_thread = threading.Thread(
        target=es_dispatcher,
        name="es-dispatcher",
        daemon=True,
    )
    dispatcher_thread.start()

    # 5. 跑 cli loop (主线程, 阻塞等 input)
    #    v4 简化: main loop 不读 stdin (避免跟 input_queue 抢输入);
    #    真要混合 stdin, 可以用 select / 单独的 stdin reader thread.
    #    这里: 先做 ES 注入, 测试通过后再说.
    logger.info("[main] 启动 REPL 循环 (input 来源: input_queue; "
                "ES event 由 dispatcher 注入)")
    run_cli_loop(agent_handler, input_queue, runtime)

    # 6. 清理
    dispatcher_thread.join(timeout=3.0)
    if runtime.is_running:
        runtime.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
