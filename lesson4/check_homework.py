#!/usr/bin/env python3
"""
Lesson 4 自测脚本: 不需要 LLM Key、不联网, 只验证工具与 ReAct 链路的契约.

运行 (先按 README 第 0 步装好 lesson4 环境):
    cd lesson4 && python check_homework.py

8 个测试分三层:
- test_01-06   工具: 6 个工具经 ToolManager 真实调用 (临时沙箱);
               test_01 验证注册表 (TODO(6)), read_file 已给 (test_02 过 = 环境正常)
- test_07-08   框架级终验: 构造**真实的** StatelessReactAgent, 把它的 llm 换成
               FakeLLM (脚本化假模型, 接口对齐 SDK 的 .request), 然后走 step() —
               SDK 真正的 ReAct 循环会解析 tool_call → 从 ToolManager 找到你注册的
               工具 → 真实执行 → 把结果回填进下一轮请求 → 返回最终 TextAction.

FakeLLM 意味着: 模型"说要写文件", SDK 循环就必须真的通过你的工具把文件写进磁盘,
并把 "successfully ..." 回填给下一轮 —— 工具必须真实执行, 伪造不了.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# 让 `python check_homework.py` 直接可跑: 导入本课 tools 包
# (构造 StatelessReactAgent 需要 api key 环境变量, 给个假值 —— 反正会被 FakeLLM 顶替,
#  永远不会真正发请求)
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-lesson4-check")
os.environ.setdefault("OPENAI_MODEL", "dummy-model")

_LESSON4_DIR = Path(__file__).resolve().parent
if str(_LESSON4_DIR) not in sys.path:
    sys.path.insert(0, str(_LESSON4_DIR))

from tongagents.agents.llm import ModelConfig, ModelProvider  # noqa: E402
from tongagents.agents.llm.messages import (  # noqa: E402
    ModelOutputMessage,
    ModelTextMessage,
    ToolCallMessage,
    ToolResultMessage,
    UserPromptMessage,
)
from tongagents.agents.llm_agent import ReactAgentSetting, StatelessReactAgent  # noqa: E402
from tongagents.agents.llm_agent.defs import LLMInputEvent  # noqa: E402
from tongagents.tools.tool_manager import ToolManager  # noqa: E402

from tools import register_default_tools  # noqa: E402
from tools.read_file_tool import ReadFileTool
from tools.write_file_tool import WriteFileTool
from tools.edit_file_tool import EditFileTool
from tools.bash_tool import BashTool
from tools.glob_tool import GlobTool
from tools.grep_tool import GrepTool

_SIX_TOOLS = {"read_file", "write_file", "edit_file", "bash", "glob", "grep"}
_TOOL_CLASSES = {
    cls.name: cls
    for cls in (ReadFileTool, WriteFileTool, EditFileTool, BashTool, GlobTool, GrepTool)
}


# ============================================================
# FakeLLM: 脚本化假模型 (接口对齐 SDK LLM 的 .request)
# ============================================================
class FakeLLM:
    """按预设剧本依次吐回复, 并记录每一轮收到的 messages / tools."""

    def __init__(self, replies: list):
        self.replies = list(replies)
        self.calls: list[tuple[list, list]] = []

    def request(self, messages, tools=[]):
        msgs = messages if isinstance(messages, list) else [messages]
        self.calls.append((msgs, list(tools)))
        if not self.replies:
            raise AssertionError("FakeLLM 剧本用完了 —— SDK 多调了一轮模型")
        return self.replies.pop(0)


def tool_reply(*calls: tuple[str, dict]) -> ModelOutputMessage:
    """构造一条"模型要调工具"的回复."""
    return ModelOutputMessage(
        tool_call_messages=[
            ToolCallMessage(
                tool_name=name,
                arguments=json.dumps(args, ensure_ascii=False),
                tool_call_id=f"call_{i}",
            )
            for i, (name, args) in enumerate(calls, start=1)
        ]
    )


def text_reply(text: str) -> ModelOutputMessage:
    """构造一条"模型给出最终文本"的回复."""
    return ModelOutputMessage(model_text_message=ModelTextMessage(content=text))


def run_agent(query: str, fake: FakeLLM) -> list:
    """构造真实 StatelessReactAgent (全部 6 工具), 换上 FakeLLM, 跑一次 step()."""
    agent = StatelessReactAgent(
        agent_settings=ReactAgentSetting(
            name="lesson4-check-agent",
            llm_config=ModelConfig(model_provider=ModelProvider.OPENAI_COMPATIBLE),
            tool_identifier_list=sorted(_SIX_TOOLS),
            system_prompt="check",
        )
    )
    agent.llm = fake  # 假 key 构造出来的真 LLM 在这里被顶替, 永远不会被调用
    return agent.step(LLMInputEvent(input=[UserPromptMessage(query)]))


def final_text(actions: list) -> str:
    for action in actions:
        if getattr(action, "is_final_response", False):
            return (action.content or "").strip()
    raise AssertionError("step() 的返回里没有 is_final_response=True 的 TextAction")


# ============================================================
# 测试
# ============================================================
class HomeworkTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lesson4-hw-")
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _call(self, name: str, **args) -> str:
        """绕过 register_default_tools 直接调某个工具 (TODO(6) 之前也能单测工具)."""
        if name not in ToolManager.tool_classes:
            ToolManager.register_tool(name, _TOOL_CLASSES[name])
        instance = ToolManager.get_tool_instance(name)
        return instance.call(json.dumps(args, ensure_ascii=False))

    # ---------- 第 1 层: 注册表与工具真实行为 ----------

    def test_01_register_default_tools(self):
        """TODO(6): register_default_tools 把 6 个工具注册进 ToolManager, schema 合法."""
        register_default_tools()
        self.assertTrue(
            _SIX_TOOLS.issubset(ToolManager.tool_classes),
            f"注册表里应包含全部 6 个工具, 实际: {sorted(ToolManager.tool_classes)}",
        )
        for name in _SIX_TOOLS:
            cls = ToolManager.tool_classes[name]
            self.assertTrue(cls.description, f"{name} 缺 description (模型靠它选工具)")
            params = cls.parameters.to_json_schema()
            self.assertEqual(params.get("type"), "object", f"{name} 的 parameters 应为 object")
            unknown = set(params.get("required", [])) - set(params.get("properties", {}))
            self.assertFalse(unknown, f"{name} required 里有未定义的参数: {unknown}")

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
        """TODO(1) write_file: 覆盖写 / 追加 / 自动建父目录 / 成功消息."""
        target = self.tmp / "sub" / "dir" / "new.txt"   # 父目录不存在
        out = self._call("write_file", path=str(target), content="hello\n")
        self.assertIn("successfully", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

        out = self._call("write_file", path=str(target), content="world\n", append=True)
        self.assertIn("successfully", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\nworld\n")

    def test_04_edit_file(self):
        """TODO(2) edit_file: 唯一匹配替换 / 未找到 / 多处匹配 —— 后两者不得改动文件."""
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
        """TODO(3) bash: 真实执行 (echo) / 失败命令有错误信息 / 空命令报错."""
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
        """TODO(4)(5): glob 按文件名找 / grep 按内容找 (含 include 与大小写开关)."""
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

    # ---------- 第 2 层: 框架级终验 (真实 SDK 循环 + FakeLLM) ----------

    def test_07_agent_loop_executes_tool_and_backfills(self):
        """真实 ReAct 循环: 模型要写文件 -> 你的工具真实执行 -> 结果回填 -> 最终回答."""
        target = self.tmp / "hello.txt"
        register_default_tools()
        fake = FakeLLM(
            [
                tool_reply(("write_file", {"path": str(target), "content": "hello lesson4"})),
                text_reply("已写入 hello.txt"),
            ]
        )

        actions = run_agent("请写入 hello.txt", fake)
        answer = final_text(actions)

        # 工具必须真实执行 (伪造不了)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello lesson4")
        self.assertEqual(answer, "已写入 hello.txt")
        self.assertEqual(len(fake.calls), 2, "应恰好调用模型 2 轮 (要工具 + 最终回答)")

        # 第 1 轮必须把注册表里的工具传给模型
        tool_names_1st = {t.name for t in fake.calls[0][1]}
        self.assertIn("write_file", tool_names_1st, "调用模型时必须带上注册表里的工具")

        # 第 2 轮请求里应有回填的 ToolResultMessage —— 这就是"工具结果回填"
        results = [m for m in fake.calls[1][0] if isinstance(m, ToolResultMessage)]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "write_file")
        self.assertIn("successfully", str(results[0].content))

    def test_08_agent_loop_parallel_tool_calls(self):
        """真实 ReAct 循环: 一轮并行要 2 个工具, 两个结果都要回填, 循环继续."""
        target = self.tmp / "par.txt"
        register_default_tools()
        fake = FakeLLM(
            [
                tool_reply(
                    ("write_file", {"path": str(target), "content": "par"}),
                    ("bash", {"command": "echo tool-b"}),
                ),
                text_reply("两件事都完成了"),
            ]
        )

        actions = run_agent("两件事", fake)
        answer = final_text(actions)

        self.assertEqual(answer, "两件事都完成了")
        self.assertTrue(target.exists(), "write_file 应真实执行")

        results = [m for m in fake.calls[1][0] if isinstance(m, ToolResultMessage)]
        self.assertEqual(len(results), 2, "两个 tool_call 都要各回填一条 ToolResultMessage")
        by_name = {r.name: str(r.content) for r in results}
        self.assertIn("successfully", by_name.get("write_file", ""))
        self.assertIn("tool-b", by_name.get("bash", ""), "bash 应真实执行")


if __name__ == "__main__":
    unittest.main(verbosity=2, exit=False)
    print()
    print(f"工具: {len(_SIX_TOOLS & set(ToolManager.tool_classes))}/6 已注册进 ToolManager")
    print("全部通过后, 配好 .env 运行 python cli_file_sample.py 接真模型 (README 第 8 步)")
