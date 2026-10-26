"""精确字符串替换工具 — TODO(2)."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tongagents.tools.base import Tool, ToolParameters


class EditFileTool(Tool):
    """精确字符串替换 (old_string → new_string)."""

    name: ClassVar[str] = "edit_file"
    description: ClassVar[str] = """对已有文件做精确字符串替换 (不重写整个文件).

参数:
- path: 文件路径 (必需, 文件必须已存在)
- old_string: 待替换的原文字 (必需, 必须与文件内容精确匹配且唯一出现)
- new_string: 替换后的新文字 (必需, 空串表示删除)

示例:
- {"path": "x.md", "old_string": "name: A", "new_string": "name: B"}
"""
    parameters: ClassVar[ToolParameters] = ToolParameters(
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径 (必需)"},
                "old_string": {"type": "string", "description": "待替换的原文字 (精确匹配)"},
                "new_string": {"type": "string", "description": "替换后的新文字 (空串=删除)"},
            },
            "required": ["path", "old_string", "new_string"],
        }
    )
    name_for_human: ClassVar[str] = "Edit File"
    args_format: ClassVar[str] = "json"

    def _do_call(self, params: dict, **kwargs) -> str:
        """TODO(2): 精确替换, 一次只许改一处.

        提示 (四处校验, 任何一处失败都**不得改动文件**):
        - path 为空 / old_string 为空  -> "error: ... 不能为空"
        - 文件不存在                   -> f"error: 文件不存在: {path}"
        - original.count(old_string) == 0 -> "error: old_string 在 {path} 中未找到; ..."
        - 出现次数 > 1                 -> "error: ... 出现 {n} 次, 无法决定替换哪一处; 请提供更精确的上下文"
        - 恰好 1 次: replace(old, new, 1) 写回 -> f"successfully edited file: {path}"
        """
        path = params.get("path", "")
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")

        # TODO(2): 删除下面这行, 按提示实现
        raise NotImplementedError("Lesson 4 TODO(2): 实现 EditFileTool._do_call")
