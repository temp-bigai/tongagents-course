"""Simplified EventSource package (cli-sample-with-event-soource).

参考 Tong-Agent 的 tongagents_cli.event_source 实现, 但极简化:
- 不依赖 storage / event_store / daemon (这些是持久化/后台进程机制, 教学不必要)
- 不依赖 tongagents_sdk dispatcher (事件流向简化: Source -> Runtime.queue -> Handler)
- 只保留最小可用: TimerEventSource + Runtime + Event dataclass

设计目标:
- 一眼看懂 eventsource 是什么 (Source 产生 Event, 通过 Runtime 分发给 Handler)
- 真跑得动 (2 秒间隔的 Timer + CLI 打印)
- 跟 cli-sample/tools/ 同级: tools/ 是 Agent 工具, event_source/ 是事件源 (互补不冲突)
"""
from .runtime import Event, EventSourceRuntime
from .timer_source import TimerEventSource

__all__ = [
    "Event",
    "EventSourceRuntime",
    "TimerEventSource",
]
