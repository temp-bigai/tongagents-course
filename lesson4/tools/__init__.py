"""
lesson4 本地工具集 — 学生自己重写的 6 个 OS 工具

组织方式对照 ../cli-sample/tools/: 一个工具一个文件, Tool 子类三件套
(name/description/parameters + _do_call), 最后统一注册到 SDK 的 ToolManager.
与 cli-sample 的区别: 这里的 _do_call 由你**自己实现** (read_file 已给样例).

注册方式 (TODO(6) 完成后):

    from tools import register_default_tools
    register_default_tools()  # 注册到 tongagents.ToolManager, 之后才能被 Agent 选用
"""
from __future__ import annotations

from tongagents.tools.tool_manager import ToolManager

from .read_file_tool import ReadFileTool
from .write_file_tool import WriteFileTool
from .edit_file_tool import EditFileTool
from .bash_tool import BashTool
from .glob_tool import GlobTool
from .grep_tool import GrepTool

# 6 个本地工具 (与 cli-sample 同名同类名, 便于对照).
_DEFAULT_TOOL_CLASSES = [
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    BashTool,
    GlobTool,
    GrepTool,
]


def register_default_tools() -> None:
    """TODO(6): 把 6 个工具类注册到 tongagents ToolManager.

    提示 (对照 ../cli-sample/tools/__init__.py):
    - 逐个 cls 调 ToolManager.register_tool(cls.name, cls)
    - 幂等: cls.name 已在 ToolManager.tool_classes 里就跳过
      (重复注册同名工具, SDK 行为不可预期)
    """
    # TODO(6): 删除下面这行, 按提示实现
    raise NotImplementedError("Lesson 4 TODO(6): 实现 register_default_tools")


__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "BashTool",
    "GlobTool",
    "GrepTool",
    "register_default_tools",
]
