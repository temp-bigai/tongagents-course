"""Bash 命令执行工具 (简化版, 从 tongagents_cli.default_agent.tools.BashTool 复制).

差异 (vs SDK):
- 无 sandbox hook / sandbox backend (cli-sample 本地直跑)
- 无 interactive command 检测 (极简版)
- 用 subprocess.run + shlex.split 安全执行
"""
from __future__ import annotations

import os
import shlex
import subprocess
from typing import ClassVar

from tongagents.tools.base import Tool, ToolParameters


class BashTool(Tool):
    """执行 shell 命令 (本地直接执行, 无沙箱)."""

    name: ClassVar[str] = "bash"
    description: ClassVar[str] = """执行 Shell 命令.

参数:
- command: 要执行的命令 (必需)
- timeout: 超时时间 (秒), 默认 30
- working_dir: 工作目录 (可选)

示例:
- {"command": "ls -la"}
- {"command": "python train.py", "timeout": 60}
- {"command": "git status"}
"""
    parameters: ClassVar[ToolParameters] = ToolParameters(
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令 (必需)"},
                "timeout": {"type": "integer", "description": "超时时间 (秒)", "default": 30, "minimum": 1},
                "working_dir": {"type": "string", "description": "执行命令的工作目录 (可选)"},
            },
            "required": ["command"],
        }
    )
    name_for_human: ClassVar[str] = "Bash"
    args_format: ClassVar[str] = "json"

    def _do_call(self, params: dict, **kwargs) -> str:
        command = params.get("command", "")
        timeout = params.get("timeout", 30)
        working_dir = params.get("working_dir")

        if not command:
            return "error: command 不能为空"

        try:
            # shlex 安全解析, 避免命令注入
            cmd_args = shlex.split(command)

            # 同步当前进程环境
            result = subprocess.run(
                cmd_args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
                env=os.environ.copy(),
            )

            output = []
            if result.stdout:
                output.append(f"[stdout]\n{result.stdout}")
            if result.stderr:
                output.append(f"[stderr]\n{result.stderr}")
            if result.returncode != 0 and not result.stdout and not result.stderr:
                output.append(f"[exit code: {result.returncode}]")

            return "\n".join(output) if output else "(command completed, no output)"

        except ValueError as e:
            return f"error: 命令解析失败 - {e}"
        except subprocess.TimeoutExpired:
            return f"error: 命令执行超时 ({timeout}秒)"
        except FileNotFoundError as e:
            return f"error: 命令不存在 - {e}"
        except Exception as e:
            return f"error: {e}"