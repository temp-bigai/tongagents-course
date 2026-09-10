"""CliEventHandler - 控制台打印 handler.

教学版 handler, 参考 Tong-Agent tongagents_cli.event_source.handlers.lark_cli:
- Tong-Agent 的 handler 一般会把事件桥接到 LLM Agent (喂 prompt, 让 Agent 干活)
- 我们这里简化: 直接打印到控制台, 演示"事件被 handler 收到并处理"

如果以后想接 LLM:
- 把 _handle_tick() 改成: 调用 SDK Agent.step(UserPromptMessage(prompt))
- 或者: 把 Event 转成 LLMInputEvent, 让 Agent 决定下一步
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("handler.cli")


class CliEventHandler:
    """控制台 handler: 收到事件就打印, 触发业务占位逻辑."""

    def __init__(self, name: str = "cli_console") -> None:
        self.name = name

    def handle(self, event: Any) -> None:
        """统一入口: 根据 event.type 分发到具体处理函数."""
        logger.info("[%s] 收到事件: %s", self.name, event)

        handler_method = getattr(self, f"_handle_{event.type.replace('.', '_')}", None)
        if handler_method is None:
            logger.info(
                "[%s] 未知事件类型 %s, 跳过业务处理 (只打印)",
                self.name,
                event.type,
            )
            return
        handler_method(event)

    # ------------------------------------------------------------------
    # 业务处理: timer.tick 触发时
    # ------------------------------------------------------------------

    def _handle_timer_tick(self, event: Any) -> None:
        """处理定时 tick 事件. 这里是业务占位, 真实场景可以:
        - 调用外部 API
        - 触发 SDK Agent 处理
        - 写文件 / 发通知 / 清理缓存
        """
        tick = event.payload.get("tick", 0)
        note = event.payload.get("note", "")
        logger.info(
            "[%s] [业务] 处理 timer.tick #%d%s",
            self.name,
            tick,
            f" ({note})" if note else "",
        )

        # 示例: 每 5 个 tick 模拟一个"昂贵操作"
        if tick > 0 and tick % 5 == 0:
            logger.info(
                "[%s] [业务] 达到 %d 个 tick 里程碑, 触发扩展动作",
                self.name,
                tick,
            )
