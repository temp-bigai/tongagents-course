"""读文件工具 — 已给完整样例, 照这个模式写另外 5 个.

结构对照 ../cli-sample/tools/read_file_tool.py (SDK 参考版, 可读);
本目录是你要自己重写的版本. 三件套缺一不可:
1. ClassVar name / description / parameters — SDK 把它们发给模型做 function calling,
   description 写不清, 模型就不会选这个工具;
2. parameters 是 OpenAI JSON Schema 格式 (ToolParameters 包装);
3. _do_call(self, params, **kwargs) — 真正的执行体, params 是模型给的参数 dict.

约定 (与 cli-sample 一致): 成功返回人类可读字符串; 失败也不抛异常,
返回 "error: ..." 字符串 — 错误要能回传给模型, 抛异常会中断整轮对话.
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

            lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
            total = len(lines)
            start = min(offset, total)
            end = min(offset + limit, total)

            header = f"=== {path} (lines {start + 1}-{end}/{total}) ===\n"
            return header + "\n" + "".join(lines[start:end])
        except UnicodeDecodeError:
            return f"error: 文件不是 UTF-8 编码: {path}"
        except Exception as e:
            return f"error: {e}"
