"""Simplified EventSource Runtime (cli-sample-with-event-soource).

教学版 EventSource Runtime. 核心抽象:

    Source ──emit(Event)──▶ Runtime.queue ──dispatch──▶ Handler.handle(Event)
                                     │
                                     └─ bindings: source.name -> [handler]

参考 Tong-Agent tongagents_cli.event_source.runtime (Task #1900+):
- Tong-Agent 是单例 (get_runtime), 配合 daemon + storage 做持久化
- 我们这里简化为直接构造, 只服务进程内生命周期

简化点 (相对 Tong-Agent):
1. 没有 storage / event_store 持久化
2. 没有 daemon 后台进程 (直接前台跑, Ctrl+C 停)
3. 没有 SDK dispatcher 耦合 (这里只是 Event -> Handler, 不触发 LLM)
4. bindings 用 dict[source_name, list[handler]] 而不是注册回调
"""
from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("event_source.runtime")


@dataclass
class Event:
    """事件数据结构.

    Attributes:
        type: 事件类型 (e.g. 'timer.tick', 'user.message', 'webhook.github')
        source: 产生该事件的 source 名称 (e.g. 'sample_timer')
        payload: 事件载荷, 自由 dict
        timestamp: ISO-8601 时间戳, 默认当前时间
    """

    type: str
    source: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat(timespec="seconds")

    def __str__(self) -> str:
        return (
            f"Event[{self.type}] from {self.source} @ {self.timestamp} "
            f"payload={self.payload}"
        )


# 一个事件 source 必须实现的最小协议: start(emit_cb) / stop()
SourceLike = Any  # duck-typed


class EventSourceRuntime:
    """进程内 EventSource Runtime: 持有 source/handler 注册表 + 派发循环.

    Usage (模式 1, 默认 — handler dispatch)::

        runtime = EventSourceRuntime()
        runtime.add_source(timer_es)
        runtime.add_handler(cli_handler)
        runtime.bind(timer_es, cli_handler)
        runtime.start()              # 内部 dispatcher 线程会调 cli_handler.handle(event)
        # 或者: runtime.start(); do_other_stuff(); runtime.stop()

    Usage (模式 2, 外部消费 — external consumer)::

        runtime = EventSourceRuntime(auto_dispatch=False)
        runtime.add_source(timer_es)
        runtime.start()
        # 外部代码自己从 runtime._queue (或 runtime.get_event()) 拿 Event
        # 适用于: event 走 user input loop / event 转其他协议 / 多消费者场景

    Threading:
    - 派发循环跑在 daemon 线程, 从 queue 拿 Event 分发给绑定 handler
      (仅在 auto_dispatch=True 时)
    - Source 的 emit 是 thread-safe (queue.Queue)
    """

    def __init__(
        self,
        auto_stop_when_all_sources_finish: bool = True,
        auto_dispatch: bool = True,
    ) -> None:
        """
        Args:
            auto_stop_when_all_sources_finish:
                所有 source 都自然结束时是否自动 stop runtime. 默认 True.
            auto_dispatch:
                是否启动内部 dispatcher 线程 (从 _queue 拿 Event -> handler.handle).
                - True (默认): 经典模式, Source -> Runtime -> Handler
                - False: 外部消费模式, Source -> Runtime._queue (外部自己 get)
                  适用于 event 转 user input / 跨进程传递 / 自定义 dispatch 逻辑
                  等场景. v4 cli-sample-with-event-soource 用这个模式:
                  event 不直接给 handler, 而是包装成 user input 注入 REPL.
        """
        self._sources: List[SourceLike] = []
        self._handlers: List[Any] = []
        # source_name -> [handler, ...]
        self._bindings: Dict[str, List[Any]] = {}
        self._queue: "queue.Queue[Event]" = queue.Queue()
        self._running: bool = False
        self._dispatcher_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        # 当所有 source 都自然结束时 (比如 TimerEventSource 达到 max_count 自动退),
        # 是否自动停掉 runtime. 默认 True, 让 main.py 不需要外部打断.
        self._auto_stop_when_all_sources_finish = auto_stop_when_all_sources_finish
        # 内部 dispatcher 线程是否从 _queue 消费. False 时外部代码自己 get.
        self._auto_dispatch = auto_dispatch
        # source.name -> 线程对象 (用来判断 source 是否还活着)
        self._source_threads: Dict[str, Optional[threading.Thread]] = {}

    # ------------------------------------------------------------------
    # 注册 API
    # ------------------------------------------------------------------

    def add_source(self, source: SourceLike) -> None:
        """注册一个事件源. 源必须实现 start(emit_cb) / stop()."""
        with self._lock:
            if source in self._sources:
                logger.warning("Source already registered: %s", source.name)
                return
            self._sources.append(source)
            self._bindings.setdefault(source.name, [])
        logger.info("Registered source: %s (type=%s)", source.name, type(source).__name__)

    def add_handler(self, handler: Any) -> None:
        """注册一个事件 handler. Handler 必须有 name 属性 + handle(event) 方法."""
        with self._lock:
            if handler in self._handlers:
                logger.warning("Handler already registered: %s", handler.name)
                return
            self._handlers.append(handler)
        logger.info("Registered handler: %s (type=%s)", handler.name, type(handler).__name__)

    def bind(self, source: SourceLike, handler: Any) -> None:
        """绑定 source -> handler. 绑定后 source 产生的 Event 都会派发到该 handler."""
        with self._lock:
            self._bindings.setdefault(source.name, []).append(handler)
        logger.info("Bound %s -> %s", source.name, handler.name)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动派发线程 + 所有 source. 启动后 Runtime 进入 running 状态.

        auto_dispatch=False 时不启动内部 dispatcher 线程, 留给外部消费.
        """
        with self._lock:
            if self._running:
                logger.warning("Runtime already running")
                return
            self._running = True

        # 启动派发线程 (仅在 auto_dispatch=True 时)
        if self._auto_dispatch:
            self._dispatcher_thread = threading.Thread(
                target=self._dispatch_loop,
                name="event-source-dispatcher",
                daemon=True,
            )
            self._dispatcher_thread.start()
            logger.info("内部 dispatcher 线程已启动")
        else:
            logger.info(
                "auto_dispatch=False, 跳过内部 dispatcher; "
                "外部代码请用 get_event() 或 _queue.get() 消费 Event"
            )

        # 启动所有 source (把 emit 回调传过去, 并跟踪线程句柄)
        for source in self._sources:
            try:
                source.start(self._emit)
                # source 内部会用 threading.Thread 启动, 我们通过 name 找它
                # (约定: TimerEventSource 用 name=f"timer-source-{self.name}")
                thread = self._find_source_thread(source.name)
                self._source_threads[source.name] = thread
                logger.info("Source started: %s (thread=%s)", source.name, thread.name if thread else "?")
            except Exception:
                logger.exception("Failed to start source: %s", source.name)

    def _find_source_thread(self, source_name: str) -> Optional[threading.Thread]:
        """根据 source.name 找到对应的线程 (靠线程名前缀匹配)."""
        candidates = [
            t for t in threading.enumerate()
            if t.name.startswith("timer-source-")
            and t.name.endswith(source_name)
        ]
        return candidates[0] if candidates else None

    def stop(self) -> None:
        """停止所有 source + 派发线程. 幂等."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        # 停止所有 source
        for source in self._sources:
            try:
                source.stop()
            except Exception:
                logger.exception("Error stopping source: %s", source.name)

        # 等派发线程退出 (最多 5 秒)
        if self._dispatcher_thread and self._dispatcher_thread.is_alive():
            self._dispatcher_thread.join(timeout=5.0)

        logger.info("Runtime stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # 内部: emit + dispatch
    # ------------------------------------------------------------------

    def _emit(self, event: Event) -> None:
        """Source 调用的回调: 把 Event 塞进 queue."""
        self._queue.put(event)

    def get_event(self, timeout: float = 0.5) -> Optional[Event]:
        """从 queue 拿 Event (外部消费者用, auto_dispatch=False 模式).

        Args:
            timeout: 阻塞超时 (秒). None 表示永久阻塞 (不建议, 没法优雅退出).

        Returns:
            Event 或 None (timeout 时).
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _dispatch_loop(self) -> None:
        """派发循环 (跑在 daemon 线程). 从 queue 拿 Event 派发给 binding 的 handler."""
        logger.info("Dispatcher loop started")
        while self._running or not self._queue.empty():
            try:
                event = self._queue.get(timeout=0.5)
            except queue.Empty:
                # 检查是否所有 source 都自然结束 -> 自动停
                if (
                    self._auto_stop_when_all_sources_finish
                    and self._sources
                    and all(self._is_source_done(s) for s in self._sources)
                ):
                    logger.info("所有 source 都自然结束, runtime auto-stopping")
                    self._running = False
                    break
                continue
            with self._lock:
                handlers = list(self._bindings.get(event.source, []))
            for handler in handlers:
                try:
                    handler.handle(event)
                except Exception:
                    logger.exception(
                        "Handler %s failed to handle %s", handler.name, event
                    )
        logger.info("Dispatcher loop exited")

    def _is_source_done(self, source: SourceLike) -> bool:
        """判断 source 是否已经结束 (线程不在 alive 状态)."""
        thread = self._source_threads.get(source.name)
        if thread is None:
            return False
        return not thread.is_alive()
