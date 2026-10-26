#!/usr/bin/env python3
"""
Lesson 6 自测脚本: 不需要 LLM / 网络, 只验证 FileMemory 与框架的契约.

运行 (先按 README 第 0 步装好 lesson6 环境, 任意装好 tongagents 的解释器均可):
    cd lesson6 && python check_memory.py

8 个测试全部通过, 说明你的 FileMemory 达到了接入 ReActAgentWithMemory 的契约;
其中 test_08 是框架级终验 (SlidingWindowRAGContextWindowManager 真实恢复链路).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

# 让 `python check_memory.py` 直接可跑: 把 lesson6/ 加入 sys.path 以导入 memory 包
_LESSON6_DIR = Path(__file__).resolve().parent
if str(_LESSON6_DIR) not in sys.path:
    sys.path.insert(0, str(_LESSON6_DIR))

from memory import FileMemory  # noqa: E402

from tongagents.agents.context_window.base import ChatHistoryUnit  # noqa: E402
from tongagents.agents.context_window.sliding_window_rag_context_window_manager import (  # noqa: E402
    SlidingWindowRAGContextWindowManager,
)
from tongagents.agents.llm.messages import (  # noqa: E402
    ModelOutputMessage,
    ModelTextMessage,
    UserPromptMessage,
)
from tongagents.memory.memory import MemoryBase, SimpleMemory  # noqa: E402
from tongagents.message.message import (  # noqa: E402
    Message,
    MessageChunk,
    MessageRole,
)

# 框架恢复上下文时传入的反序列化器 (与 SlidingWindowRAGContextWindowManager 内部一致)
UNIT_DESERIALIZERS = {ChatHistoryUnit.__name__: ChatHistoryUnit.load}


def make_done_unit(question: str, answer: str) -> ChatHistoryUnit:
    """构造一个已完成 (is_done=True) 的对话单元: 用户问 + 助手答."""
    unit = ChatHistoryUnit()
    unit.add_message(UserPromptMessage(content=question))
    unit.add_message(
        ModelOutputMessage(model_text_message=ModelTextMessage(content=answer))
    )
    assert unit.is_done()
    return unit


class FileMemoryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "paper_memory.jsonl"

    def memory(self, session_id="paper-review", agent_id="paper-agent") -> FileMemory:
        return FileMemory(self.path, agent_id=agent_id, session_id=session_id)

    # --------------------------------------------------------
    # test_01: 写入产生合法 JSONL, 且带类型标签
    # --------------------------------------------------------
    def test_01_add_chunk_writes_jsonl_with_type_tag(self):
        mem = self.memory()
        mem.add_chunk(make_done_unit("Q1", "A1"), role=MessageRole.ASSISTANT)

        lines = self.path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1, "应恰好写入 1 行")
        record = json.loads(lines[0])
        self.assertEqual(record["serial_name"], "ChatHistoryUnit", "必须有类型标签")
        self.assertEqual(record["role"], "assistant")
        self.assertEqual(
            record["meta_data"].get("session_id"), "paper-review",
            "meta_data 里必须有 session_id, 否则无法按会话过滤",
        )

    # --------------------------------------------------------
    # test_02: 模拟重启 (新实例) + 传入 config 还原为原对象
    # --------------------------------------------------------
    def test_02_new_instance_restores_objects(self):
        self.memory().add_chunk(make_done_unit("检索 memory 论文", "综述正文 ABC"))

        restarted = self.memory()  # 新进程里 new 出来的新实例
        msgs = restarted.get_messages(config=UNIT_DESERIALIZERS)
        self.assertEqual(len(msgs), 1)
        content = msgs[0].chunks[0].content
        self.assertIsInstance(content, ChatHistoryUnit, "必须还原为对象而非字符串")
        self.assertEqual(content.message_list[0].content, "检索 memory 论文")
        self.assertEqual(
            content.message_list[1].model_text_message.content, "综述正文 ABC"
        )

    # --------------------------------------------------------
    # test_03: 不传 config 时返回字符串 (这正是框架要求传 config 的原因)
    # --------------------------------------------------------
    def test_03_without_config_returns_str(self):
        self.memory().add_chunk(make_done_unit("Q", "A"))
        msgs = self.memory().get_messages()  # 不传 config
        self.assertEqual(len(msgs), 1)
        self.assertIsInstance(msgs[0].chunks[0].content, str)

    # --------------------------------------------------------
    # test_04: 同一文件混存多个 session, 读取按 session 过滤
    # --------------------------------------------------------
    def test_04_session_filter(self):
        mem_a = self.memory(session_id="session-A")
        mem_b = self.memory(session_id="session-B")
        mem_a.add_chunk(make_done_unit("A-1", "答案A1"))
        mem_b.add_chunk(make_done_unit("B-1", "答案B1"))

        got_a = self.memory(session_id="session-A").get_messages(config=UNIT_DESERIALIZERS)
        self.assertEqual(len(got_a), 1, "只应看到 session-A 自己的记录")
        self.assertIn("A1", got_a[0].chunks[0].content.dump())

        got_b = mem_b.get_messages(session_id="session-B", config=UNIT_DESERIALIZERS)
        self.assertEqual(len(got_b), 1)
        self.assertIn("B1", got_b[0].chunks[0].content.dump())

    # --------------------------------------------------------
    # test_05: recent_n 只取最近 n 条 (时间顺序的尾部)
    # --------------------------------------------------------
    def test_05_recent_n_tail(self):
        mem = self.memory()
        for i in range(3):
            mem.add_chunk(make_done_unit(f"Q{i}", f"A{i}"))
            time.sleep(0.01)  # 保证 timestamp 单调

        msgs = mem.get_messages(recent_n=2, config=UNIT_DESERIALIZERS)
        self.assertEqual(len(msgs), 2)
        dump_texts = [m.chunks[0].content.dump() for m in msgs]
        self.assertIn("A2", dump_texts[-1], "最新的记录应在尾部")
        self.assertNotIn("A0", "".join(dump_texts), "最旧的记录应被截掉")

    # --------------------------------------------------------
    # test_06: clear 只清当前 session, 不动别人的
    # --------------------------------------------------------
    def test_06_clear_only_current_session(self):
        self.memory(session_id="session-A").add_chunk(make_done_unit("A", "ans-A"))
        self.memory(session_id="session-B").add_chunk(make_done_unit("B", "ans-B"))

        self.memory(session_id="session-A").clear()

        remaining = self.memory(session_id="session-B").get_messages(
            config=UNIT_DESERIALIZERS
        )
        self.assertEqual(len(remaining), 1, "session-B 的记录必须保留")
        empty = self.memory(session_id="session-A").get_messages(
            config=UNIT_DESERIALIZERS
        )
        self.assertEqual(len(empty), 0, "session-A 的记录应被清空")

    # --------------------------------------------------------
    # test_07: 如果还原失败 (content 是字符串), 框架会抛 ValueError
    #          —— 这是设计好的失败信号, 不是 bug
    # --------------------------------------------------------
    def test_07_manager_rejects_string_content(self):
        class BrokenMemory(MemoryBase):
            """故意不还原对象的错误实现, 用于观察框架的报错."""

            def add_chunk(self, content, role=MessageRole.UNSPECIFIED,
                          require_upload=False):
                pass

            def add_chunks(self, chunks, role=MessageRole.UNSPECIFIED):
                pass

            def add_message(self, message):
                pass

            def add_messages(self, messages):
                pass

            def get_messages(self, session_id=None, recent_n=None, **kwargs):
                return [Message(chunks=[MessageChunk(content="我是一个字符串, 不是对象")])]

            def clear(self):
                pass

        with self.assertRaises(ValueError) as ctx:
            SlidingWindowRAGContextWindowManager(memory=BrokenMemory())
        self.assertIn("Invalid message type", str(ctx.exception))

    # --------------------------------------------------------
    # test_08: 框架级终验 — 真实的"落库 → 重启 → 恢复"链路 (无 LLM)
    # --------------------------------------------------------
    def test_08_manager_save_then_restore(self):
        # 第 1 轮: 用 manager 正常走一轮对话 (用户问 -> 助手答 -> unit 终态落库)
        mem = self.memory()
        mgr = SlidingWindowRAGContextWindowManager(
            max_history_len=5, system_prompt="你是论文综述 agent", memory=mem
        )
        mgr.add_message(UserPromptMessage(content="检索 LLM agent memory 论文"))
        mgr.add_message(
            ModelOutputMessage(
                model_text_message=ModelTextMessage(content="综述正文: 共 5 篇论文…")
            )
        )
        self.assertEqual(len(mgr.chat_history), 1)

        # 重启: 新的 manager + 新的 FileMemory 实例, 同一文件与 session
        restarted_mgr = SlidingWindowRAGContextWindowManager(
            max_history_len=5,
            system_prompt="你是论文综述 agent",
            memory=self.memory(),  # "新进程"里的新实例
        )
        self.assertEqual(len(restarted_mgr.chat_history), 1, "应恢复出 1 轮对话")

        def texts(messages):
            out = []
            for m in messages:
                if hasattr(m, "model_text_message") and m.model_text_message:
                    out.append(m.model_text_message.content or "")
                else:
                    out.append(getattr(m, "content", "") or "")
            return "\n".join(out)

        prompt = texts(restarted_mgr.get_prompt())
        self.assertIn("检索 LLM agent memory 论文", prompt, "上一轮问题应在上下文中")
        self.assertIn("综述正文", prompt, "上一轮综述应在上下文中 — 这就是'记得'")


if __name__ == "__main__":
    print(f"SimpleMemory (参考): {SimpleMemory()}  — 对照: 它重启即失忆\n")
    unittest.main(verbosity=2)
