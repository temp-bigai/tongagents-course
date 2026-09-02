"""Grep 内容搜索工具 (简化版, 从 tongagents_cli.default_agent.tools.GrepTool 复制)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from tongagents.tools.base import Tool, ToolParameters


class GrepTool(Tool):
    """在文件中搜索匹配的内容 (支持正则)."""

    name: ClassVar[str] = "grep"
    description: ClassVar[str] = """在文件中搜索匹配的内容 (支持正则).

参数:
- pattern: 搜索模式 (必需, 支持正则)
- path: 搜索目录 (可选, 默认 ".")
- include: 文件过滤 (可选), e.g. "*.py"
- case_sensitive: 大小写敏感 (默认 true)
- max_matches: 最大匹配数 (默认 100)

输出格式:
file.py:10:matched line content

示例:
- {"pattern": "def my_function", "include": "*.py"}
- {"pattern": "TODO", "include": "*.md"}
- {"pattern": "hello", "case_sensitive": false}
"""
    parameters: ClassVar[ToolParameters] = ToolParameters(
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "搜索模式 (支持正则)"},
                "path": {"type": "string", "description": "搜索目录 (可选)"},
                "include": {"type": "string", "description": "文件过滤模式 (e.g. *.py)"},
                "case_sensitive": {"type": "boolean", "description": "是否大小写敏感", "default": True},
                "max_matches": {"type": "integer", "description": "最大匹配数", "default": 100},
            },
            "required": ["pattern"],
        }
    )
    name_for_human: ClassVar[str] = "Grep"
    args_format: ClassVar[str] = "json"

    def _do_call(self, params: dict, **kwargs) -> str:
        pattern = params.get("pattern", "")
        search_path = params.get("path", ".")
        include = params.get("include", "")
        case_sensitive = params.get("case_sensitive", True)
        max_matches = params.get("max_matches", 100)

        if not pattern:
            return "error: pattern 不能为空"

        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)

            matches: list[str] = []
            search_path_obj = Path(search_path)

            if not search_path_obj.exists():
                return f"error: 路径不存在: {search_path}"

            for file_path in search_path_obj.rglob("*"):
                if not file_path.is_file():
                    continue

                # 文件过滤
                if include:
                    if not file_path.match(include):
                        continue

                # 跳过大于 10MB 的文件
                if file_path.stat().st_size > 10 * 1024 * 1024:
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_no, line in enumerate(f, 1):
                            if regex.search(line):
                                matches.append(f"{file_path}:{line_no}:{line.rstrip()}")
                                if len(matches) >= max_matches:
                                    break
                except Exception:
                    continue

                if len(matches) >= max_matches:
                    break

            if not matches:
                return f"no matches for '{pattern}'"

            total = len(matches)
            header = f"found {total} matches:\n"
            if total == max_matches:
                header = f"found {total} matches (capped):\n"

            return header + "\n".join(matches[:max_matches])

        except re.error as e:
            return f"error: 无效的正则表达式: {e}"
        except Exception as e:
            return f"error: {e}"