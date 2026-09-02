"""写文件工具 (简化版, 从 tongagents_cli.default_agent.tools.WriteFileTool 复制)."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tongagents.tools.base import Tool, ToolParameters


class WriteFileTool(Tool):
    """写入/追加文件, 自动创建父目录."""

    name: ClassVar[str] = "write_file"
    description: ClassVar[str] = """写入内容到文件.

参数:
- path: 文件路径 (必需)
- content: 文件内容 (必需)
- append: 追加模式 (默认 false = 覆盖)

示例:
- {"path": "hello.py", "content": "print('Hello!')"}
- {"path": "log.txt", "content": "new line\\n", "append": true}
"""
    parameters: ClassVar[ToolParameters] = ToolParameters(
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径 (必需)"},
                "content": {"type": "string", "description": "文件内容 (必需)"},
                "append": {"type": "boolean", "description": "追加模式 (true=追加, false=覆盖)", "default": False},
            },
            "required": ["path", "content"],
        }
    )
    name_for_human: ClassVar[str] = "Write File"
    args_format: ClassVar[str] = "json"

    def _do_call(self, params: dict, **kwargs) -> str:
        path = params.get("path", "")
        content = params.get("content", "")
        append = params.get("append", False)

        if not path:
            return "error: path 不能为空"

        try:
            file_path = Path(path)

            # 自动创建父目录
            file_path.parent.mkdir(parents=True, exist_ok=True)

            mode = "a" if append else "w"
            with open(file_path, mode, encoding="utf-8") as f:
                f.write(content)

            action = "appended to" if append else "wrote"
            return f"successfully {action} file: {path}"

        except Exception as e:
            return f"error: {e}"