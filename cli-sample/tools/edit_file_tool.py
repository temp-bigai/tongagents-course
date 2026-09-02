"""精确字符串替换工具 (简化版, 从 tongagents_cli.default_agent.tools.EditFileTool 复制).

对已有文件做精确字符串替换, 不重写整个文件.
适用于:
- 修正某段特定内容
- 在不破坏其他段落的前提下插入/删除/替换文字
- 比 write_file 更省 token、更快、且对 trace 友好
"""
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
- old_string: 待替换的原文字 (必需, 必须与文件内容精确匹配)
- new_string: 替换后的新文字 (必需, 空串表示删除)

注意事项:
- old_string 必须**精确**匹配文件中某段连续内容 (含空格/换行/缩进)
- 找不到 old_string → 返回错误, 不修改文件
- 多次替换请分多次调用

示例:
- {"path": "x.md", "old_string": "name: A", "new_string": "name: B"}
- {"path": "x.md", "old_string": "deprecated: true\\n", "new_string": ""}
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
        path = params.get("path", "")
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")

        if not path:
            return "error: path 不能为空"
        if old_string == "":
            return "error: old_string 不能为空"

        file_path = Path(path)
        if not file_path.exists():
            return f"error: 文件不存在: {path}"

        try:
            original = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            return f"error: 读取文件失败: {exc}"

        # 必须唯一匹配, 避免误替换
        occurrences = original.count(old_string)
        if occurrences == 0:
            return (
                f"error: old_string 在 {path} 中未找到; "
                "请确认文件内容与待替换字符串完全一致 (含空格/换行/缩进)"
            )
        if occurrences > 1:
            return (
                f"error: old_string 在 {path} 中出现 {occurrences} 次, "
                "无法决定替换哪一处; 请提供更精确的上下文"
            )

        updated = original.replace(old_string, new_string, 1)
        try:
            file_path.write_text(updated, encoding="utf-8")
        except Exception as exc:
            return f"error: 写入文件失败: {exc}"

        return f"successfully edited file: {path}"