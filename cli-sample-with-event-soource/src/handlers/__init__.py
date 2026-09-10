"""CLI Event Handlers package (cli-sample-with-event-soource).

教学版 handler 集合, 跟 Tong-Agent tongagents_cli.event_source.handlers 对齐 (简化版):
- CliEventHandler: 控制台打印 + 业务占位 (Timer tick 触发时打印)
- AgentHandler: 把 Event 包装成 user query, 调 mini agent loop + tools (Task #3468)

使用建议:
- 教学 v1 入门: CliEventHandler (只打印)
- 教学 v2 进阶: AgentHandler (event -> user query -> agent 处理 + tools)
"""
from .agent_handler import AgentHandler
from .cli_handler import CliEventHandler

__all__ = ["AgentHandler", "CliEventHandler"]