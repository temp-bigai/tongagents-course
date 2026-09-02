"""Glob 模式匹配工具 (简化版, 从 tongagents_cli.default_agent.tools.GlobTool 复制)."""
from __future__ import annotations

import os
from glob import glob as glob_pattern
from typing import ClassVar

from tongagents.tools.base import Tool, ToolParameters


class GlobTool(Tool):
    """用通配符模式查找文件."""

    name: ClassVar[str] = "glob"
    description: ClassVar[str] = """使用通配符模式查找文件.

参数:
- pattern: 通配符模式 (必需), e.g. "**/*.py"
- path: 搜索根目录 (可选, 默认 ".")
- max_results: 最大返回数量 (默认 100)

示例:
- {"pattern": "**/*.py"}
- {"pattern": "**/*.md"}
- {"pattern": "**/test_*.py", "path": "src"}
"""
    parameters: ClassVar[ToolParameters] = ToolParameters(
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "通配符模式 (必需), e.g. **/*.py"},
                "path": {"type": "string", "description": "搜索根目录 (可选)"},
                "max_results": {"type": "integer", "description": "最大返回数量", "default": 100},
            },
            "required": ["pattern"],
        }
    )
    name_for_human: ClassVar[str] = "Glob"
    args_format: ClassVar[str] = "json"

    def _do_call(self, params: dict, **kwargs) -> str:
        pattern = params.get("pattern", "")
        search_path = params.get("path", ".")
        max_results = params.get("max_results", 100)

        if not pattern:
            return "error: pattern 不能为空"

        try:
            if not os.path.isabs(search_path):
                search_path = os.path.join(os.getcwd(), search_path)

            full_pattern = os.path.join(search_path, pattern)
            matches = glob_pattern(full_pattern, recursive=True)

            if not matches:
                return f"no files matched '{pattern}'"

            if len(matches) > max_results:
                return (
                    f"found {len(matches)} matches (showing first {max_results}):\n"
                    + "\n".join(matches[:max_results])
                )

            return f"found {len(matches)} matches:\n" + "\n".join(matches)

        except Exception as e:
            return f"error: {e}"