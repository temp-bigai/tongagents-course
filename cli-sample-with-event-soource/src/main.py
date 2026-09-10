#!/usr/bin/env python3
"""CLI Sample with EventSource + Agent - 教学示例 (Task #3468).

跟 cli-sample/cli_sample.py 配套:
- cli-sample 演示 "Agent + Tools" (LLM 调用本地工具)
- cli-sample-with-event-soource 演示 "EventSource + Agent" (定时触发 -> agent 处理)

v2 (Task #3468) 升级:
- 不再只打印日志, 而是: Event -> 包装成 user query -> 调 mini agent loop -> 用 tools 处理
- 类似 Tong-Agent cli.act(query): user query -> workflow.stream(query) -> 输出
- 这里: TimerEventSource emit Event -> AgentHandler.handle -> 4 个真实 tools 跑通

工作流:
    1. 构造 EventSourceRuntime
    2. 注册 TimerEventSource (每 N 秒触发, max_count=M 后自动停)
    3. 注册 AgentHandler (v2 新, 把 event 当 user query 处理)
    4. bind source -> handler
    5. runtime.start()  -> 后台线程开始派发
    6. 主线程 sleep, 让定时器有空间触发
    7. Ctrl+C / max_count 到达 -> runtime.stop() 退出

用法::

    cd cli-sample-with-event-soource/src
    python3 main.py
    # 或者改 interval: 修改 main.py 里的 INTERVAL_SECONDS

环境变量:
    EVENT_INTERVAL_SECONDS: 定时间隔 (默认 30)
    EVENT_MAX_COUNT: 最大触发次数 (默认 5)
    EVENT_LOG_FILE: agent handler 写入的日志文件 (默认 /tmp/es_agent_log.txt)
    EVENT_HANDLER: 'agent' (默认 v2) 或 'cli' (v1 旧版, 只打印)
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path

# 让脚本能找到本地 event_source/handlers 包
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from event_source import EventSourceRuntime, TimerEventSource  # noqa: E402
from handlers import AgentHandler, CliEventHandler  # noqa: E402


# ============================================================================
# 日志配置: 教学用清晰格式, 一眼看到是谁在打日志
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli-sample-with-event-soource")


# ============================================================================
# 配置 (支持环境变量覆盖, 方便测试和 CI)
# ============================================================================
INTERVAL_SECONDS = float(os.getenv("EVENT_INTERVAL_SECONDS", "30"))
MAX_COUNT = int(os.getenv("EVENT_MAX_COUNT", "5"))
LOG_FILE = os.getenv("EVENT_LOG_FILE", "/tmp/es_agent_log.txt")
HANDLER_KIND = os.getenv("EVENT_HANDLER", "agent").lower()  # 'agent' (v2) or 'cli' (v1)


def build_runtime() -> EventSourceRuntime:
    """构造 + 注册 + 绑定: 把 Runtime 准备好, 不启动."""
    runtime = EventSourceRuntime()

    # 定时事件源: 每 INTERVAL_SECONDS 秒触发, MAX_COUNT 次后自动停
    timer_es = TimerEventSource(
        name="sample_timer",
        interval_seconds=INTERVAL_SECONDS,
        max_count=MAX_COUNT,
        event_type="timer.tick",
        payload={
            "source": "cli-sample-with-event-soource",
            "note": f"每 {INTERVAL_SECONDS:.0f} 秒触发一次",
        },
    )

    # Handler 选择: v2 默认 AgentHandler, v1 CliEventHandler 仅作回退
    if HANDLER_KIND == "agent":
        handler = AgentHandler(
            name="sample_agent",
            log_file=LOG_FILE,
            max_tool_calls=3,
        )
        logger.info("使用 v2 AgentHandler (event -> user query -> mini agent loop)")
    else:
        handler = CliEventHandler(name="cli_console")
        logger.info("使用 v1 CliEventHandler (仅打印, 不走 agent)")

    runtime.add_source(timer_es)
    runtime.add_handler(handler)
    runtime.bind(timer_es, handler)

    return runtime


def install_signal_handlers(runtime: EventSourceRuntime) -> None:
    """Ctrl+C / SIGTERM 优雅退出."""

    def _shutdown(signum, _frame):
        sig_name = signal.Signals(signum).name
        logger.info("收到信号 %s, 停止所有 eventsource ...", sig_name)
        runtime.stop()
        # 不要在这里 sys.exit, 让主循环看到 is_running=False 自然退出

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)


def main() -> int:
    logger.info("=" * 60)
    logger.info("CLI Sample with EventSource + Agent 启动 (Task #3468)")
    logger.info("  interval = %.1f 秒", INTERVAL_SECONDS)
    logger.info("  max_count = %d", MAX_COUNT)
    logger.info("  handler = %s", HANDLER_KIND)
    logger.info("  log_file = %s", LOG_FILE)
    logger.info("  按 Ctrl+C 提前退出")
    logger.info("=" * 60)

    runtime = build_runtime()
    install_signal_handlers(runtime)

    runtime.start()

    # 主线程保持: 看到 runtime.is_running=False 就退出
    try:
        while runtime.is_running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        # 信号 handler 已经 stop 了 runtime, 不会再进来
        logger.info("KeyboardInterrupt 兜底, 停止 runtime")
        runtime.stop()

    logger.info("=" * 60)
    logger.info("CLI Sample with EventSource + Agent 退出")
    logger.info("  日志查看: cat %s", LOG_FILE)
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())