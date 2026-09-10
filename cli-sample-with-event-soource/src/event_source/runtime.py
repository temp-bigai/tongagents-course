"""EventSource Runtime v5 — unified queue + event mechanism.

教学版 EventSource Runtime (Task #3472 v5). 核心抽象:

    Source ──emit──▶ Runtime ──route──▶ Handler ──wrap+push──▶ Runtime.input_queue
                                                              │   (统一 user + event)
                                                              ↓
                                                       cli loop get_input()

设计动机 (v4 -> v5):
    v4: ES dispatcher 线程独立存在, 把 Event 转 user input 推 input_queue;
        stdin 又独立读, 不入 input_queue. 双层 queue + 多个线程, 不合理.
    v5: EventSource 内部**拥有**统一的 input_queue (user + event 一个源);
        handler 拿到 runtime 引用, 把 event 包装推 input_queue;
        cli loop 从 runtime.get_input() 拿, 不关心来源.
        stdin reader 后台线程也直接 runtime.add_user_input(), 跟 event 走同路.

关键 API:
    runtime.input_queue       — 统一的 input queue (dict items: origin/content/timestamp)
    runtime.add_user_input()  — 外部 (cli stdin reader) 推 user input
    runtime.add_event()       — Source 触发 event, 路由到 handler
    runtime.get_input()       — cli loop 阻塞等 input (user 或 event)
    handler.handle(event, runtime) — 新签名, 接收 runtime, 可推 input_queue

参考 Tong-Agent tongagents_cli.event_source.runtime (Task #1900+), 简化点:
1. 没有 storage / event_store 持久化
2. 没有 daemon 后台进程 (前台跑, Ctrl+C 停)
3. bindings 用 dict[source_name, list[handler]] 而不是注册回调
4. 没有独立的 ES dispatcher 线程 (v5 把 dispatcher 逻辑下沉到 handler)
"""
from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

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


# 一个事件 source 必须实现的最小协议: start(runtime) / stop()
# v5 改动: source 拿到的是整个 runtime (而不是 emit callback),
# 这样 source 可以调 runtime.add_event() 触发 handler 路由.
SourceLike = Any  # duck-typed


class EventSourceRuntime:
    """进程内 EventSource Runtime (v5): 拥有统一 input_queue + event 路由.

    v5 关键改动 (相对 v4):
    - 新增 self.input_queue: dict item (origin/content/timestamp) 的 Queue
      - origin 字段: 'stdin' / 'es_event' / 自定义 tag
      - cli loop 用 self.get_input(timeout) 阻塞取 input
    - 新增 add_user_input(text, source_tag): 外部推 user input
      - 供 stdin reader 后台线程用
    - 新增 add_event(event): Source 触发 event, 路由到绑定 handler
      - handler 新签名 handle(event, runtime), 拿到 runtime 引用
      - handler 把 event 包装成 user input 推 runtime.input_queue
    - 移除 v4 的 get_event() (外部消费者用): v5 不需要, source 直接调 add_event
    - 移除 v4 的内部 _emit / _dispatch_loop / auto_dispatch 参数
      - v5 路由是同步的: source.add_event() -> handler.handle() 立即执行
      - 没有独立 dispatcher 线程, 简化

    Usage::

        runtime = EventSourceRuntime()
        timer = TimerEventSource(name='timer', interval_seconds=5, max_count=3)
        agent = AgentHandler(name='agent')
        runtime.add_source(timer)
        runtime.add_handler(agent)
        runtime.bind(timer, agent)

        # 后台 stdin reader: 读 stdin -> runtime.add_user_input()
        # main loop: runtime.get_input() -> agent.step(item['content'])

        runtime.start()  # 启动所有 source

    Threading:
    - Source 自己跑后台线程 (e.g. TimerEventSource._loop)
    - Source._loop 调 runtime.add_event(event) (线程安全, queue.Queue)
    - add_event 同步路由 handler.handle(event, runtime) (在 source 线程里跑)
    - handler.handle 调 runtime.input_queue.put (线程安全)
    - cli loop 主线程: runtime.get_input() (阻塞, timeout 循环)
    """

    def __init__(self) -> None:
        # ------------------------------------------------------------------
        # 统一 input queue (v5 新增): dict item 包含 origin/content/timestamp
        # origin 字段标识来源: 'stdin' / 'es_event:timer_name' / 自定义 tag
        # ------------------------------------------------------------------
        self.input_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()

        # 注册表 (跟 v4 一致)
        self._sources: List[SourceLike] = []
        self._handlers: List[Any] = []
        self._bindings: Dict[str, List[Any]] = {}  # source_name -> [handler]

        # 状态
        self._running: bool = False
        self._lock = threading.Lock()

        # 调试用: 记录 event 历史 (handler 处理后可查)
        self.event_history: List[Event] = []

        # 调试用: 记录 user input 历史
        self.user_input_history: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 注册 API
    # ------------------------------------------------------------------

    def add_source(self, source: SourceLike) -> None:
        """注册一个事件源. 源必须实现 start(runtime) / stop()."""
        with self._lock:
            if source in self._sources:
                logger.warning("Source already registered: %s", source.name)
                return
            self._sources.append(source)
            self._bindings.setdefault(source.name, [])
        logger.info("Registered source: %s (type=%s)", source.name, type(source).__name__)

    def add_handler(self, handler: Any) -> None:
        """注册一个事件 handler. Handler 必须有 name 属性 + handle(event, runtime) 方法."""
        with self._lock:
            if handler in self._handlers:
                logger.warning("Handler already registered: %s", handler.name)
                return
            self._handlers.append(handler)
        logger.info("Registered handler: %s (type=%s)", handler.name, type(handler).__name__)

    def bind(self, source: SourceLike, handler: Any) -> None:
        """绑定 source -> handler. 绑定后 source 产生的 Event 都会路由到该 handler."""
        with self._lock:
            self._bindings.setdefault(source.name, []).append(handler)
        logger.info("Bound %s -> %s", source.name, handler.name)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动所有 source. Source 拿到 runtime 引用 (v5 新签名).

        v5 不再有内部 dispatcher loop. Source 自己跑后台线程, 触发时
        调 runtime.add_event(event). add_event 同步路由 handler.handle().
        """
        with self._lock:
            if self._running:
                logger.warning("Runtime already running")
                return
            self._running = True

        # 启动所有 source (把 runtime 引用传过去, v5 新签名)
        for source in self._sources:
            try:
                source.start(self)
                logger.info("Source started: %s", source.name)
            except Exception:
                logger.exception("Failed to start source: %s", source.name)

    def stop(self) -> None:
        """停止所有 source. 幂等."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        for source in self._sources:
            try:
                source.stop()
            except Exception:
                logger.exception("Error stopping source: %s", source.name)

        logger.info("Runtime stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # v5 新 API: 统一 input queue
    # ------------------------------------------------------------------

    def add_user_input(self, text: str, source_tag: str = "user") -> None:
        """外部推 user input 到统一 input_queue.

        Args:
            text: user 输入文本 (已经 strip 过)
            source_tag: 来源标识 (debug 用), 默认 'user'.
                常见: 'stdin' (CLI stdin reader)

        推送格式::

            {
                'origin': source_tag,        # e.g. 'stdin'
                'content': text,             # 实际文本
                'timestamp': ISO-8601,       # 时间戳
            }
        """
        item = {
            "origin": source_tag,
            "content": text,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        self.user_input_history.append(item)
        logger.info("[input] +user (origin=%s): %s", source_tag, text[:80])
        self.input_queue.put(item)

    def add_event(self, event: Event) -> None:
        """Source 触发 event, 路由到绑定的 handler.

        v5 流程:
        1. 记录 event 到 event_history (调试)
        2. 查 bindings[event.source] -> [handler, ...]
        3. 同步调每个 handler.handle(event, runtime) (在 source 线程里)
        4. handler 内部把 event 包装成 user input 推 runtime.input_queue

        Args:
            event: Event 实例 (type/source/payload)

        注意: 这里不直接推 input_queue! 因为 handler 可能要 wrap / filter /
        dedupe event. handler 拿到 runtime 引用, 决定是否推 / 怎么推.
        """
        logger.info(
            "[event] %s.%s: payload=%s",
            event.source,
            event.type,
            event.payload,
        )
        self.event_history.append(event)

        # 路由到 handler (新签名 handle(event, runtime))
        handlers = list(self._bindings.get(event.source, []))
        if not handlers:
            logger.warning(
                "[event] no handler bound for source=%s, event dropped",
                event.source,
            )
            return
        for handler in handlers:
            try:
                handler.handle(event, self)
            except Exception:
                logger.exception(
                    "Handler %s failed to handle event %s",
                    handler.name,
                    event,
                )

    def get_input(self, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
        """cli loop 阻塞等 input (user 或 event wrap 来的).

        Args:
            timeout: 阻塞超时 (秒)

        Returns:
            dict item {'origin': ..., 'content': ..., 'timestamp': ...}
            或 None (timeout 时)

        注意: 拿到 item 后, 通过 item['origin'] 区分来源 (debug 用), 但
        agent 处理 content 时不区分 — 走同一条 agent.step() 路径.
        """
        try:
            return self.input_queue.get(timeout=timeout)
        except queue.Empty:
            return None