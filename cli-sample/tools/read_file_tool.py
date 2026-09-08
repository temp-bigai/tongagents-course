"""读文件工具 (简化版, 从 tongagents_cli.default_agent.tools.ReadFileTool 复制).

差异 (vs tongagents_cli SDK):
- 无 sandbox hook (cli-sample 本地直跑)
- 简化错误消息
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tongagents.tools.base import Tool, ToolParameters


class ReadFileTool(Tool):
    """读取文件内容, 支持 offset/limit 范围."""

    name: ClassVar[str] = "read_file"
    description: ClassVar[str] = """读取文件内容.

参数:
- path: 文件路径 (必需)
- offset: 起始行号 (默认 0)
- limit: 读取行数 (默认 2000)

示例:
- {"path": "README.md"}
- {"path": "main.py", "limit": 100}
- {"path": "main.py", "offset": 100}
"""
    parameters: ClassVar[ToolParameters] = ToolParameters(
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径 (必需)"},
                "offset": {"type": "integer", "description": "起始行号 (从0开始)", "default": 0},
                "limit": {"type": "integer", "description": "读取行数", "default": 2000},
            },
            "required": ["path"],
        }
    )
    name_for_human: ClassVar[str] = "Read File"
    args_format: ClassVar[str] = "json"

    def _do_call(self, params: dict, **kwargs) -> str:
        path = params.get("path", "")
        offset = params.get("offset", 0)
        limit = params.get("limit", 2000)

        if not path:
            return "error: path 不能为空"

        try:
            file_path = Path(path)
            if not file_path.exists():
                return f"error: 文件不存在: {path}"
            if not file_path.is_file():
                return f"error: 路径不是文件: {path}"

            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = min(offset, total_lines)
            end = min(offset + limit, total_lines)

            content = "".join(lines[start:end])
            header = f"=== {path} (lines {start + 1}-{end}/{total_lines}) ===\n"

            if offset + limit < total_lines:
                header += f"(showing lines {start + 1} to {end} of {total_lines})\n"
                header += "use offset parameter to read more...\n"

            return header + "\n" + content

        except UnicodeDecodeError:
            return f"error: 文件不是 UTF-8 编码: {path}"
        except Exception as e:
            return f"error: {e}"