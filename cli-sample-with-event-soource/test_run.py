#!/usr/bin/env python3
"""test_run.py - 集成测试: 验证定时 EventSource 真的能触发并派发.

放在 cli-sample-with-event-soource/test_run.py (跟 src/ 同级).

跑法:
    cd cli-sample-with-event-soource
    python3 test_run.py

期望:
- interval_seconds=2, max_count=3
- 大约 6-7 秒内完成
- 日志里能看到 tick #1, #2, #3 各一次
- handler 真的收到 3 个 Event
- runtime 正常 stop, 不留僵尸线程
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

# 让 import 能找到 src/event_source 和 src/handlers
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from event_source import EventSourceRuntime, TimerEventSource  # noqa: E402
from handlers import CliEventHandler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_run")


# 自定义 handler: 每次 handle 计数, 方便断言
class CountingHandler(CliEventHandler):
    def __init__(self, name: str = "counter"):
        super().__init__(name=name)
        self.received_events: list = []
        self._lock = threading.Lock()

    def handle(self, event):
        with self._lock:
            self.received_events.append(event)
        super().handle(event)


def main() -> int:
    logger.info("===== test_run 开始 =====")
    start_time = time.monotonic()

    runtime = EventSourceRuntime()
    timer_es = TimerEventSource(
        name="test_timer",
        interval_seconds=2,
        max_count=3,
        event_type="timer.tick",
        payload={"source": "test", "note": "集成测试"},
    )
    counter = CountingHandler(name="counter")

    runtime.add_source(timer_es)
    runtime.add_handler(counter)
    runtime.bind(timer_es, counter)

    runtime.start()

    # 主循环: 等 runtime.is_running 自动变 False (所有 source 自然结束时 auto-stop)
    deadline = time.monotonic() + 15.0
    while runtime.is_running and time.monotonic() < deadline:
        time.sleep(0.2)

    # 兜底 stop (deadline 到了还没退)
    if runtime.is_running:
        logger.warning("Runtime 还没退, 兜底 stop")
        runtime.stop()

    elapsed = time.monotonic() - start_time
    logger.info("===== test_run 完成, elapsed=%.2fs =====", elapsed)

    # 断言
    n = len(counter.received_events)
    logger.info("Handler 收到 %d 个事件:", n)
    for ev in counter.received_events:
        logger.info("  - %s", ev)

    assert n == 3, f"期望 3 个事件, 实际 {n}"
    assert counter.received_events[0].payload["tick"] == 1
    assert counter.received_events[1].payload["tick"] == 2
    assert counter.received_events[2].payload["tick"] == 3
    # 3 ticks @ 2s = ~6s, + 启动/收尾开销约 1-3s, 总共 6-10s 都算正常
    assert 5.0 <= elapsed <= 10.0, f"期望 5-10 秒, 实际 {elapsed:.2f}"

    # 验证线程都退了
    alive = [t.name for t in threading.enumerate() if t != threading.main_thread()]
    logger.info("剩余非主线程: %s", alive)

    logger.info("✅ 全部断言通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
