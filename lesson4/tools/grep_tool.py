"""内容正则搜索工具 — TODO(5)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from tongagents.tools.base import Tool, ToolParameters


class GrepTool(Tool):
    """在文件内容中按正则搜行 (输出 文件:行号:内容)."""

    name: ClassVar[str] = "grep"
    description: ClassVar[str] = """在文件内容中按正则搜索.

参数:
- pattern: 搜索模式 (必需, 支持正则)
- path: 搜索目录 (默认当前目录)
- include: 文件名过滤 (e.g. *.py)
- case_sensitive: 大小写敏感 (默认 true)
- max_matches: 最大匹配数 (默认 100)

示例:
- {"pattern": "def my_function", "include": "*.py"}
"""
    parameters: ClassVar[ToolParameters] = ToolParameters(
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "搜索模式 (支持正则, 必需)"},
                "path": {"type": "string", "description": "搜索目录 (可选, 默认当前目录)"},
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
        """TODO(5): 按内容找.

        提示:
        - pattern 为空 -> "error: pattern 不能为空"
        - regex = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
          (re.error -> f"error: 无效正则: {e}")
        - root = Path(path); 不存在 -> f"error: 路径不存在: {path}"
        - 遍历 sorted(root.rglob("*")) 里的是文件; include 非空时
          用 file_path.match(include) 过滤; 读取失败 (二进制等) 直接跳过
        - 命中行记 f"{file_path}:{line_no}:{line.strip()}" (行号从 1 计), 凑够 max_matches 即止
        - 无命中 -> f"no matches for '{pattern}'"; 有 -> "found {n} matches:\\n" + 命中行
        """
        pattern = params.get("pattern", "")
        path = params.get("path", ".")
        include = params.get("include", "")
        case_sensitive = params.get("case_sensitive", True)
        max_matches = params.get("max_matches", 100)

        # TODO(5): 删除下面这行, 按提示实现
        raise NotImplementedError("Lesson 4 TODO(5): 实现 GrepTool._do_call")
