"""CLI Event Handlers package (cli-sample-with-event-soource).

v4 设计 (Task #3470):
- 单 handler: AgentHandler (复用 cli-sample 的 agent, 不实现 mini loop)
- 移除 CliEventHandler — 不再有 cli_observer (用户反馈 v3 多 handler 太杂)

ES 事件处理路径 (v4):
    TimerEventSource -> EventSourceRuntime._queue
                            ↓ (ES dispatcher thread 轮询)
                         input_queue (跟 user stdin 合流)
                            ↓ (复用 cli-sample REPL 循环)
                         agent.step(user_input)
                            ↓
                         print(response)
"""
from .agent_handler import AgentHandler

__all__ = ["AgentHandler"]
