"""tools — 6 个本地文件工具 (TODO 2-6; read_file 已给样例).

每个工具三件套: 函数实现 + JSON Schema + register() 注册.
schema 已给出 (照抄参数名/类型写实现即可), 你要完成 5 个函数体.
行为对照 ../cli-sample/tools/ 的同名工具 —— 那是 SDK 版参考实现, 可读,
但请自己写: 每个函数约 10 行, 都是纯 pathlib/subprocess 操作.

约定 (与 cli-sample 一致):
- 成功: 返回人类可读的字符串 (如 "successfully wrote file: x.txt")
- 失败: 也不抛异常, 返回 "error: ..." 字符串 —— 错误要能回传给模型
"""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

from .registry import register

# ============================================================
# 1. read_file —— 已给样例: 照这个模式写下面 5 个
# ============================================================


def read_file(path: str, offset: int = 0, limit: int = 2000) -> str:
    """读取文件内容, 支持 offset/limit 按行范围读取."""
    if not path:
        return "error: path 不能为空"
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


register(
    "read_file",
    description=(
        "读取文件内容. 参数: path(必需), offset(起始行号,从0开始,默认0), "
        "limit(读取行数,默认2000). 示例: {\"path\": \"README.md\", \"limit\": 100}"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径 (必需)"},
            "offset": {"type": "integer", "description": "起始行号 (从0开始)", "default": 0},
            "limit": {"type": "integer", "description": "读取行数", "default": 2000},
        },
        "required": ["path"],
    },
    fn=read_file,
)

# ============================================================
# 2. write_file —— TODO(2)
# ============================================================


def write_file(path: str, content: str, append: bool = False) -> str:
    """TODO(2): 写文件, append=True 追加 / False 覆盖.

    提示:
    - Path(path).parent.mkdir(parents=True, exist_ok=True)  # 自动建父目录
    - open(..., mode="a" if append else "w", encoding="utf-8")
    - 成功返回 f"successfully {'appended to' if append else 'wrote'} file: {path}"
    """
    # TODO(2): 删除下面这行, 实现写文件
    raise NotImplementedError("Lesson 4 TODO(2): 实现 write_file")


register(
    "write_file",
    description=(
        "写文件 (覆盖或追加), 自动创建父目录. 参数: path(必需), content(必需), "
        "append(默认false=覆盖). 示例: {\"path\": \"log.txt\", \"content\": \"hi\\n\", \"append\": true}"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径 (必需)"},
            "content": {"type": "string", "description": "文件内容 (必需)"},
            "append": {"type": "boolean", "description": "true=追加, false=覆盖", "default": False},
        },
        "required": ["path", "content"],
    },
    fn=write_file,
)

# ============================================================
# 3. edit_file —— TODO(3)
# ============================================================


def edit_file(path: str, old_string: str, new_string: str) -> str:
    """TODO(3): 精确字符串替换 (一次一处).

    提示 (三处校验, 都失败都不能改动文件):
    - old_string 为空                -> "error: old_string 不能为空"
    - 文件不存在                     -> "error: 文件不存在: {path}"
    - old_string 出现 0 次           -> "error: old_string 在 {path} 中未找到; ..."
    - old_string 出现多次(>1)        -> "error: ... 出现 N 次, 无法决定替换哪一处; 请提供更精确的上下文"
    - 成功 (恰好 1 次)               -> 原地替换一次并写回, 返回 f"successfully edited file: {path}"
    """
    # TODO(3): 删除下面这行, 实现精确替换
    raise NotImplementedError("Lesson 4 TODO(3): 实现 edit_file")


register(
    "edit_file",
    description=(
        "精确字符串替换 (old_string 必须与文件内容精确匹配且唯一出现). "
        "参数: path(必需), old_string(必需), new_string(必需, 空串=删除). "
        "示例: {\"path\": \"x.md\", \"old_string\": \"name: A\", \"new_string\": \"name: B\"}"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径 (必需)"},
            "old_string": {"type": "string", "description": "待替换的原文字 (精确匹配, 必须唯一)"},
            "new_string": {"type": "string", "description": "替换后的新文字 (空串=删除)"},
        },
        "required": ["path", "old_string", "new_string"],
    },
    fn=edit_file,
)

# ============================================================
# 4. bash —— TODO(4)
# ============================================================


def bash(command: str, timeout: int = 30, working_dir: str | None = None) -> str:
    """TODO(4): 执行 shell 命令 (白名单外的命令也能跑, 靠 timeout 兜底).

    提示:
    - 参数为空返回 "error: command 不能为空"
    - shlex.split(command) 安全分词, shell=False
    - subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=working_dir)
    - 拼输出: [stdout].../[stderr]... 都带上; 全空且退出码非 0 -> "[exit code: N]"
    - subprocess.TimeoutExpired -> "error: 命令超时 ({timeout}s)"
    """
    # TODO(4): 删除下面这行, 实现命令执行
    raise NotImplementedError("Lesson 4 TODO(4): 实现 bash")


register(
    "bash",
    description=(
        "执行 shell 命令 (ls/cat/git/grep 等, 有超时保护). "
        "参数: command(必需), timeout(秒,默认30), working_dir(可选). "
        "示例: {\"command\": \"ls -la\", \"working_dir\": \"/tmp\"}"
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令 (必需)"},
            "timeout": {"type": "integer", "description": "超时时间 (秒)", "default": 30, "minimum": 1},
            "working_dir": {"type": "string", "description": "工作目录 (可选)"},
        },
        "required": ["command"],
    },
    fn=bash,
)

# ============================================================
# 5. glob —— TODO(5)
# ============================================================


def glob(pattern: str, path: str = ".", max_results: int = 100) -> str:
    """TODO(5): 按通配符模式递归找文件名.

    提示:
    - Path(path) 不存在 -> "error: 路径不存在: {path}"
    - Path(path).glob(pattern) 递归匹配 (pattern 里 ** 需要配合 rglob 或 glob("**/..."))
    - 无匹配 -> f"no files matched '{pattern}'"
    - 有匹配 -> "found N matches:\\n" + 每行一个路径 (超过 max_results 截断并注明)
    """
    # TODO(5): 删除下面这行, 实现文件名匹配
    raise NotImplementedError("Lesson 4 TODO(5): 实现 glob")


register(
    "glob",
    description=(
        "按通配符模式查找文件名 (支持 ** 递归). "
        "参数: pattern(必需, e.g. **/*.py), path(搜索根目录,默认当前目录), "
        "max_results(默认100). 示例: {\"pattern\": \"**/test_*.py\", \"path\": \"src\"}"
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "通配符模式 (必需), e.g. **/*.py"},
            "path": {"type": "string", "description": "搜索根目录 (可选, 默认当前目录)"},
            "max_results": {"type": "integer", "description": "最大返回数量", "default": 100},
        },
        "required": ["pattern"],
    },
    fn=glob,
)

# ============================================================
# 6. grep —— TODO(6)
# ============================================================


def grep(
    pattern: str,
    path: str = ".",
    include: str = "",
    case_sensitive: bool = True,
    max_matches: int = 100,
) -> str:
    """TODO(6): 在文件内容里按正则搜行.

    提示:
    - re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
    - Path(path).rglob("*") 遍历文件; include 非空时用 file_path.match(include) 过滤
    - 每个匹配行记 "文件路径:行号:该行内容" (行号从 1 计), 最多 max_matches 条
    - 输出 "found N matches:\\n" + 匹配行; 无匹配 -> f"no matches for '{pattern}'"
    """
    # TODO(6): 删除下面这行, 实现内容搜索
    raise NotImplementedError("Lesson 4 TODO(6): 实现 grep")


register(
    "grep",
    description=(
        "在文件内容中按正则搜索 (输出 文件:行号:内容). "
        "参数: pattern(必需, 支持正则), include(文件名过滤, e.g. *.py), "
        "case_sensitive(默认true), max_matches(默认100). "
        "示例: {\"pattern\": \"def my_function\", \"include\": \"*.py\"}"
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "搜索模式 (支持正则, 必需)"},
            "path": {"type": "string", "description": "搜索目录 (可选, 默认当前目录)"},
            "include": {"type": "string", "description": "文件过滤模式 (e.g. *.py)"},
            "case_sensitive": {"type": "boolean", "description": "是否大小写敏感", "default": True},
            "max_matches": {"type": "integer", "description": "最大匹配数", "default": 100},
        },
        "required": ["pattern"],
    },
    fn=grep,
)
