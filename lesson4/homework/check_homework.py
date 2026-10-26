#!/usr/bin/env python3
"""Lesson 4 课后作业自测: 不需要 API Key、不联网.

运行 (先按 README 第 0 步装好环境):
    cd lesson4/homework && python check_homework.py

覆盖三层:
- test_01      注册表: 6 个工具已注册, schema 形状合法 (OpenAI function calling 格式)
- test_02-06   工具: read/write/edit/bash/glob/grep 在临时沙箱里的真实行为
- test_07-09   循环: 用 FakeLLM (脚本化假模型) 驱动你的 agent_loop ——
               不联网也能验证 模型调用参数 / 工具真实执行 / 结果按协议回填 / 终止条件

FakeLLM 模拟 openai 返回的 message (含 .content / .tool_calls / .id / .function),
你的 agent_loop 拿到什么就执行什么 —— 所以工具必须**真的**被执行, 伪造不了.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HOMEWORK_DIR = Path(__file__).resolve().parent
if str(_HOMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(_HOMEWORK_DIR))

from mycli import tools  # noqa: E402, F401  # import 即完成 6 个工具的注册
from mycli.agent import agent_loop  # noqa: E402
from mycli.llm import llm_chat  # noqa: E402
from mycli.registry import TOOLS, TOOL_REGISTRY, call_tool  # noqa: E402

_SIX_TOOLS = {"read_file", "write_file", "edit_file", "bash", "glob", "grep"}


# ============================================================
# FakeLLM: 脚本化假模型 (形状对齐 openai 的返回值)
# ============================================================
class _FakeFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id: str, name: str, args: dict):
        self.id = call_id
        self.function = _FakeFunction(name, json.dumps(args, ensure_ascii=False))


class _FakeMessage:
    """模拟 openai 的 assistant message: content / tool_calls 二选一."""

    role = "assistant"

    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeLLM:
    """按预设脚本依次吐回复, 并记录每一轮收到的 messages / tools."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[list] = []       # 每轮收到的 messages 快照
        self.tools_seen: list = []        # 每轮收到的 tools 参数

    def __call__(self, messages, tools=None):
        self.calls.append(list(messages))
        self.tools_seen.append(tools)
        if not self.replies:
            raise AssertionError("FakeLLM 剧本用完了 —— 你的循环多调了一轮模型")
        return self.replies.pop(0)


class AlwaysToolLLM:
    """永远要调工具的模型 —— 用来验证 max_turns 兜底."""

    role = "assistant"

    def __init__(self):
        self.count = 0

    def __call__(self, messages, tools=None):
        self.count += 1
        return _FakeMessage(
            tool_calls=[_FakeToolCall(f"call_{self.count}", "bash", {"command": "echo again"})]
        )


# ============================================================
# 断言辅助: messages 里 dict / message 对象混存 (学生两种写法都合法)
# ============================================================
def _role(m) -> str:
    if isinstance(m, dict):
        return str(m.get("role", ""))
    return str(getattr(m, "role", ""))


def _tool_messages(messages) -> list[dict]:
    return [m for m in messages if isinstance(m, dict) and m.get("role") == "tool"]


def _wants_tools(m) -> bool:
    if isinstance(m, dict):
        return bool(m.get("tool_calls"))
    return bool(getattr(m, "tool_calls", None))


# ============================================================
# 测试
# ============================================================
class HomeworkTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lesson4-hw-")
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    # ---------- 第 1 层: 注册表 ----------

    def test_01_registry_six_tools_with_valid_schema(self):
        """6 个工具都已注册, schema 是合法的 OpenAI function calling 格式."""
        self.assertEqual(set(TOOL_REGISTRY), _SIX_TOOLS, "注册表里应有且仅有 6 个工具")
        self.assertEqual(len(TOOLS), 6, "TOOLS schema 列表应有 6 项")
        for spec in TOOLS:
            self.assertEqual(spec.get("type"), "function")
            fn = spec.get("function", {})
            name, params = fn.get("name"), fn.get("parameters", {})
            self.assertIn(name, _SIX_TOOLS)
            self.assertTrue(fn.get("description"), f"{name} 缺 description (模型靠它选工具)")
            self.assertEqual(params.get("type"), "object")
            unknown = set(params.get("required", [])) - set(params.get("properties", {}))
            self.assertFalse(unknown, f"{name} required 里有未定义的参数: {unknown}")
        # llm.py 的接线: llm_chat 必须可调用 (TODO(1) 完成与否这里只查存在性)
        self.assertTrue(callable(llm_chat))

    # ---------- 第 2 层: 工具真实行为 (临时沙箱) ----------

    def _call(self, name: str, **args) -> str:
        return call_tool(name, json.dumps(args, ensure_ascii=False))

    def test_02_read_file_given_example(self):
        """read_file (已给样例): 正常读 / offset+limit 切片 / 文件不存在报错."""
        f = self.tmp / "note.txt"
        f.write_text("l1\nl2\nl3\n", encoding="utf-8")

        out = self._call("read_file", path=str(f))
        self.assertIn("l1", out)
        self.assertIn("note.txt", out)

        out = self._call("read_file", path=str(f), offset=1, limit=1)
        self.assertIn("l2", out)
        self.assertNotIn("l1\n", out)

        out = self._call("read_file", path=str(self.tmp / "nope.txt"))
        self.assertIn("error", out)

    def test_03_write_file(self):
        """write_file: 覆盖写 / 追加 / 自动建父目录 / 成功消息."""
        target = self.tmp / "sub" / "dir" / "new.txt"   # 父目录不存在
        out = self._call("write_file", path=str(target), content="hello\n")
        self.assertIn("successfully", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

        out = self._call("write_file", path=str(target), content="world\n", append=True)
        self.assertIn("successfully", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\nworld\n")

    def test_04_edit_file(self):
        """edit_file: 唯一匹配替换 / 未找到 / 多处匹配 —— 后两者不得改动文件."""
        f = self.tmp / "x.md"
        f.write_text("name: A\nflag: true\n", encoding="utf-8")

        out = self._call("edit_file", path=str(f), old_string="name: A", new_string="name: B")
        self.assertIn("successfully", out)
        self.assertIn("name: B", f.read_text(encoding="utf-8"))

        out = self._call("edit_file", path=str(f), old_string="name: Z", new_string="name: Q")
        self.assertIn("error", out)
        self.assertNotIn("name: Q", f.read_text(encoding="utf-8"))

        g = self.tmp / "dup.md"
        g.write_text("x = 1\nx = 2\n", encoding="utf-8")
        out = self._call("edit_file", path=str(g), old_string="x", new_string="y")
        self.assertIn("error", out)  # 出现 2 次, 拒绝替换
        self.assertEqual(g.read_text(encoding="utf-8"), "x = 1\nx = 2\n")

    def test_05_bash(self):
        """bash: 真实执行 (echo) / 失败命令有错误信息 / 空命令报错."""
        out = self._call("bash", command="echo hello-lesson4")
        self.assertIn("hello-lesson4", out)

        out = self._call("bash", command="ls /definitely-not-exist-xyz-123")
        self.assertTrue(
            ("error" in out) or ("[stderr]" in out) or ("exit code" in out),
            f"失败命令应带回错误信息, 实际: {out!r}",
        )

        out = self._call("bash", command="")
        self.assertIn("error", out)

    def test_06_glob_and_grep(self):
        """glob 按文件名找 / grep 按内容找 (含 include 与大小写开关)."""
        (self.tmp / "a.py").write_text("def foo():\n    pass\n", encoding="utf-8")
        (self.tmp / "b.txt").write_text("hello world\n", encoding="utf-8")
        sub = self.tmp / "sub"
        sub.mkdir()
        (sub / "c.py").write_text("def bar():\n    pass\n", encoding="utf-8")

        out = self._call("glob", pattern="**/*.py", path=str(self.tmp))
        self.assertIn("a.py", out)
        self.assertIn("c.py", out)
        self.assertNotIn("b.txt", out)

        out = self._call("grep", pattern="^def", path=str(self.tmp), include="*.py")
        self.assertIn("a.py:1:", out)
        self.assertIn("c.py:1:", out)
        self.assertNotIn("b.txt", out)

        out = self._call("grep", pattern="HELLO", path=str(self.tmp))
        self.assertIn("no match", out)  # 默认大小写敏感
        out = self._call("grep", pattern="HELLO", path=str(self.tmp), case_sensitive=False)
        self.assertIn("b.txt:1:", out)

    # ---------- 第 3 层: ReAct 循环 (FakeLLM 驱动, 不联网) ----------

    def test_07_loop_executes_tool_and_backfills(self):
        """循环单工具: 模型要写文件 -> 工具真实执行 -> 结果按协议回填 -> 最终回答."""
        target = self.tmp / "hello.txt"
        fake = FakeLLM(
            [
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall("call_1", "write_file",
                                      {"path": str(target), "content": "hello lesson4"})
                    ]
                ),
                _FakeMessage(content="已写入 hello.txt"),
            ]
        )
        answer, messages = agent_loop(
            "请写入 hello.txt", system="sys-test", llm=fake, verbose=False
        )

        # 工具必须真实执行 (伪造不了)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello lesson4")
        self.assertEqual(answer, "已写入 hello.txt")
        self.assertEqual(len(fake.calls), 2, "应恰好调用模型 2 轮 (要工具 + 最终回答)")

        # 第 1 轮必须把工具 schema 传给模型
        self.assertTrue(fake.tools_seen[0], "调用模型时必须传 tools=TOOLS")
        names = {t["function"]["name"] for t in fake.tools_seen[0]}
        self.assertIn("write_file", names)

        # 消息轨迹: system, user, assistant(带 tool_calls), tool(回填)
        self.assertEqual(_role(messages[0]), "system")
        self.assertEqual(_role(messages[1]), "user")
        assistant_idx = next(i for i, m in enumerate(messages) if _wants_tools(m))
        tool_msgs = _tool_messages(messages)
        self.assertEqual(len(tool_msgs), 1)
        self.assertLess(assistant_idx, messages.index(tool_msgs[0]),
                        "assistant 消息 (含 tool_calls) 必须先于 tool 结果回传")
        self.assertEqual(tool_msgs[0].get("tool_call_id"), "call_1",
                         "tool 消息的 tool_call_id 必须与请求对应")
        self.assertIn("successfully", tool_msgs[0].get("content", ""))

    def test_08_loop_parallel_calls_and_unknown_tool(self):
        """循环多工具: 一轮并行调 2 个工具; 未知工具也要作为 error 结果回填, 循环继续."""
        fake = FakeLLM(
            [
                _FakeMessage(
                    tool_calls=[
                        _FakeToolCall("call_a", "bash", {"command": "echo tool-a"}),
                        _FakeToolCall("call_b", "no_such_tool", {"x": 1}),
                    ]
                ),
                _FakeMessage(content="done"),
            ]
        )
        answer, messages = agent_loop("两件事", llm=fake, verbose=False)

        self.assertEqual(answer, "done")
        self.assertEqual(len(fake.calls), 2)
        tool_msgs = _tool_messages(messages)
        self.assertEqual(len(tool_msgs), 2, "两个 tool_call 都要各回填一条 tool 消息")
        by_id = {m.get("tool_call_id"): m.get("content", "") for m in tool_msgs}
        self.assertIn("tool-a", by_id.get("call_a", ""), "bash 应真实执行")
        self.assertIn("未知工具", by_id.get("call_b", ""), "未知工具返回 error 字符串而非崩溃")

    def test_09_loop_max_turns_guard(self):
        """max_turns 兜底: 模型永远要工具时, 循环必须终止, 恰好调用 max_turns 轮."""
        fake = AlwaysToolLLM()
        answer, messages = agent_loop("死循环测试", max_turns=3, llm=fake, verbose=False)

        self.assertIsInstance(answer, str)  # 返回兜底文案而不是卡死/崩溃
        self.assertEqual(fake.count, 3, "应恰好调用模型 max_turns=3 次")
        self.assertEqual(len(_tool_messages(messages)), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2, exit=False)
    print()
    print(f"工具: {len(TOOL_REGISTRY)} 个已注册 ({', '.join(sorted(TOOL_REGISTRY))})")
    print("全部通过后, 配好 .env 运行 python main.py 接真模型 (README 第 7 步)")
