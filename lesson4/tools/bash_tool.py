"""执行 shell 命令工具 — TODO(3)."""
from __future__ import annotations

import shlex
import subprocess
from typing import ClassVar

from tongagents.tools.base import Tool, ToolParameters


class BashTool(Tool):
    """执行 shell 命令 (shlex 分词, subprocess 直跑, 带超时)."""

    name: ClassVar[str] = "bash"
    description: ClassVar[str] = """执行 shell 命令并返回输出.

参数:
- command: 命令 (必需)
- timeout: 超时秒数 (默认 30)
- working_dir: 工作目录 (可选)

示例:
- {"command": "ls -la"}
- {"command": "grep -r TODO src", "working_dir": "/tmp"}
"""
    parameters: ClassVar[ToolParameters] = ToolParameters(
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令 (必需)"},
                "timeout": {"type": "integer", "description": "超时时间 (秒)", "default": 30},
                "working_dir": {"type": "string", "description": "工作目录 (可选)"},
            },
            "required": ["command"],
        }
    )
    name_for_human: ClassVar[str] = "Bash"
    args_format: ClassVar[str] = "json"

    def _do_call(self, params: dict, **kwargs) -> str:
        """TODO(3): 真实执行命令.

        提示:
        - command 为空 -> "error: command 不能为空"
        - cmd = shlex.split(command)  # 安全分词, 不要 shell=True
        - subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=working_dir)
        - 拼输出: stdout/stderr 都带上 (如 "[stdout]\\n..." / "[stderr]\\n...");
          两者都空且 returncode != 0 -> f"[exit code: {proc.returncode}]";
          两者都空且成功 -> 返回一个成功提示
        - subprocess.TimeoutExpired -> f"error: 命令超时 ({timeout}s)"
        """
        command = params.get("command", "")
        timeout = params.get("timeout", 30)
        working_dir = params.get("working_dir")

        # TODO(3): 删除下面这行, 按提示实现
        raise NotImplementedError("Lesson 4 TODO(3): 实现 BashTool._do_call")
