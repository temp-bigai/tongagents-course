"""文件名通配符匹配工具 — TODO(4)."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tongagents.tools.base import Tool, ToolParameters


class GlobTool(Tool):
    """按通配符模式查找文件名 (支持 ** 递归)."""

    name: ClassVar[str] = "glob"
    description: ClassVar[str] = """按通配符模式查找文件名.

参数:
- pattern: 通配符模式 (必需, e.g. **/*.py)
- path: 搜索根目录 (默认当前目录)
- max_results: 最大返回数量 (默认 100)

示例:
- {"pattern": "**/test_*.py", "path": "src"}
"""
    parameters: ClassVar[ToolParameters] = ToolParameters(
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "通配符模式 (必需), e.g. **/*.py"},
                "path": {"type": "string", "description": "搜索根目录 (可选, 默认当前目录)"},
                "max_results": {"type": "integer", "description": "最大返回数量", "default": 100},
            },
            "required": ["pattern"],
        }
    )
    name_for_human: ClassVar[str] = "Glob"
    args_format: ClassVar[str] = "json"

    def _do_call(self, params: dict, **kwargs) -> str:
        """TODO(4): 按文件名找.

        提示:
        - pattern 为空 -> "error: pattern 不能为空"
        - root = Path(path); root 不存在 -> f"error: 路径不存在: {path}"
        - matches = sorted(p for p in root.glob(pattern) if p.is_file())
        - 无匹配 -> f"no files matched '{pattern}'"
        - 有匹配 -> "found {n} matches:\\n" + 每行一个路径 (排序, 截断到 max_results 并注明)
        """
        pattern = params.get("pattern", "")
        path = params.get("path", ".")
        max_results = params.get("max_results", 100)

        # TODO(4): 删除下面这行, 按提示实现
        raise NotImplementedError("Lesson 4 TODO(4): 实现 GlobTool._do_call")
