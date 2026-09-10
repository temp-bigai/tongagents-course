"""TimerEventSource v5 — 定时事件源, 触发时调 runtime.add_event().

教学版 timer, 参考 Tong-Agent tongagents_cli.event_source.handlers.TimerHandler (Task #1524+):

Tong-Agent 实现:
- BaseHandler 子类
- 支持 interval (毫秒) 或 cron 表达式
- 触发后通过 SDK dispatcher 注入 Event 到 Agent
- 完整持久化 + daemon 生命周期

简化点 (本实现):
1. interval 用秒 (而不是毫秒), 更直观
2. 不依赖 croniter (教学示例, interval 已经够用)
3. 不走 SDK dispatcher, 直接 emit 给 Runtime (v5: runtime.add_event)
4. 可选 max_count (到 N 次自动停), 方便测试
5. 不持久化, 不走 daemon

v5 改动 (相对 v4):
- start(runtime) 而非 start(emit_callback): Source 拿到整个 runtime 引用
- _loop(runtime) 而非 _loop(emit_callback): 触发时 runtime.add_event(event)
- 不再有 self._emit 局部变量; 直接走 runtime

Config (构造参数):
    name: 源标识
    interval_seconds: 触发间隔 (秒), 必须 > 0
    max_count: 最多触发次数 (None = 无限), 用于测试或限次任务
    event_type: emit 出去的 Event.type (默认 'timer.tick')
    payload: 附加到 Event.payload 的固定字段 (每次触发都带)
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from .runtime import Event, EventSourceRuntime

logger = logging.getLogger("event_source.timer")


class TimerEventSource:
    """按固定间隔 emit Event 的定时事件源 (v5)."""

    def __init__(
        self,
        name: str,
        interval_seconds: float = 30.0,
        max_count: Optional[int] = None,
        event_type: str = "timer.tick",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError(f"interval_seconds must be > 0, got {interval_seconds}")
        if max_count is not None and max_count <= 0:
            raise ValueError(f"max_count must be > 0 or None, got {max_count}")

        self.name = name
        self.interval_seconds = float(interval_seconds)
        self.max_count = max_count
        self.event_type = event_type
        self.payload: Dict[str, Any] = dict(payload or {})

        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._count = 0
        self._started = False

    # ------------------------------------------------------------------
    # Source protocol (v5)
    # ------------------------------------------------------------------

    def start(self, runtime: EventSourceRuntime) -> None:
        """启动定时线程. runtime 用来触发 event (runtime.add_event).

        v5: start(runtime) 而不是 start(emit_callback). Source 自己跑线程,
        触发时直接调 runtime.add_event(event) -> runtime 内部路由到 handler.
        """
        if self._started:
            logger.warning("[%s] already started", self.name)
            return

        self._stop_flag.clear()
        self._started = True
        logger.info(
            "[%s] started, interval=%.1fs, max_count=%s, event_type=%s",
            self.name,
            self.interval_seconds,
            self.max_count,
            self.event_type,
        )

        self._thread = threading.Thread(
            target=self._loop,
            args=(runtime,),
            name=f"timer-source-{self.name}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """设置停止标志, 等线程退出."""
        if not self._started:
            return
        self._stop_flag.set()
        if self._thread and self._thread.is_alive():
            # 等线程退出 (最多 2 个 interval)
            self._thread.join(timeout=max(2.0, self.interval_seconds * 2))
        self._started = False
        logger.info("[%s] stopped, total triggered=%d", self.name, self._count)

    # ------------------------------------------------------------------
    # 内部: 主循环 (v5 简化, 无 emit_callback 局部变量)
    # ------------------------------------------------------------------

    def _loop(self, runtime: EventSourceRuntime) -> None:
        """定时器主循环: 每 interval_seconds 触发一次, 直到 stop 或 max_count."""
        # 用 Event.wait 而不是 time.sleep, 这样 stop() 能即时唤醒
        while not self._stop_flag.is_set():
            # 等待一个 interval, 但能被 stop_flag 打断
            if self._stop_flag.wait(timeout=self.interval_seconds):
                break  # 被 stop 唤醒

            if self._stop_flag.is_set():
                break

            self._count += 1
            event = Event(
                type=self.event_type,
                source=self.name,
                payload={**self.payload, "tick": self._count},
            )
            try:
                # v5: 直接调 runtime.add_event, 由 runtime 路由到 handler
                runtime.add_event(event)
            except Exception:
                logger.exception("[%s] runtime.add_event raised", self.name)

            if self.max_count is not None and self._count >= self.max_count:
                logger.info(
                    "[%s] reached max_count=%d, auto-stopping",
                    self.name,
                    self.max_count,
                )
                break

        logger.info("[%s] loop exited after %d ticks", self.name, self._count)