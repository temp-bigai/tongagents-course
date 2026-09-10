"""CLI Event Handlers package (cli-sample-with-event-soource).

教学版 handler 集合, 跟 Tong-Agent tongagents_cli.event_source.handlers 对齐 (简化版):
- CliEventHandler: 控制台打印 + 业务占位 (Timer tick 触发时打印)
"""
from .cli_handler import CliEventHandler

__all__ = ["CliEventHandler"]
