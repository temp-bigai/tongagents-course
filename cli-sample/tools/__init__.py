"""
cli-sample 本地工具集

不复用 tongagents_cli.default_agent.tools (避免依赖 tongagents-cli).
直接复制 SDK 6 个核心 OS 工具的简化实现到本地, 注册到 tongagents.ToolManager.

工具:
    ReadFileTool    - 读文件
    WriteFileTool   - 写文件
    EditFileTool    - 精确字符串替换
    BashTool        - 执行 shell 命令
    GlobTool        - 文件名通配符匹配
    GrepTool        - 内容正则搜索

注册调用方式:

    from cli_sample.tools import register_default_tools
    register_default_tools()  # 自动注册到 tongagents ToolManager
"""
from __future__ import annotations

from tongagents.tools.tool_manager import ToolManager

from .read_file_tool import ReadFileTool
from .write_file_tool import WriteFileTool
from .edit_file_tool import EditFileTool
from .bash_tool import BashTool
from .glob_tool import GlobTool
from .grep_tool import GrepTool


# 6 个核心 OS 工具, 与 tongagents_cli.default_agent.tools 中的类名一致.
# 极简版不依赖 tongagents-cli, 不注册 ExaSearch / DelegateTask / QueryBackground / StopTask.
_DEFAULT_TOOL_CLASSES = [
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    BashTool,
    GlobTool,
    GrepTool,
]


def register_default_tools() -> None:
    """注册 cli-sample 默认 6 工具到 tongagents ToolManager.

    幂等: 重复调用不会重复注册 (同名工具会被 SDK 跳过/覆盖).
    """
    for cls in _DEFAULT_TOOL_CLASSES:
        if cls.name in ToolManager.tool_classes:
            continue  # 已注册, 跳过 (避免覆盖警告)
        ToolManager.register_tool(cls.name, cls)


__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "BashTool",
    "GlobTool",
    "GrepTool",
    "register_default_tools",
]