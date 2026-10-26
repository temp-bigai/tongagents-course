"""
FileMemory: 学生实现的文件持久化记忆 (Lesson 6)

参考实现:
- tongagents/memory/memory.py        -> MemoryBase 接口 + SimpleMemory (内存版, 不落盘)
- tongagents/memory/sql_engine.py    -> PersistenceMemory 背后的 SQL 引擎:
    * 写入: _insert()         记录 serial_name = type(content).__name__ + content.dump()
    * 读取: convert_chunks()  用调用方传入的 config 反序列化器按 serial_name 还原对象
- tongagents/agents/context_window/sliding_window_rag_context_window_manager.py
    -> 框架如何读写 memory (本作业的"甲方"):
    * 初始化读: _get_recent_chat_units()  调 memory.get_messages(recent_n, config=...)
                并要求 chunks[0].content 还原为 ChatHistoryUnit 对象, 类型不对直接 ValueError
    * 终态写:   _save_chat_unit_to_memory()  调 memory.add_chunk(content=unit)

存储格式 (JSONL, 每行一条):
    {"timestamp": ..., "role": "...", "meta_data": {"agent_id": ..., "session_id": ...},
     "serial_name": "ChatHistoryUnit", "content": "<dump() 出来的字符串>"}
"""

from __future__ import annotations

import json
from pathlib import Path

from tongagents.memory.memory import MemoryBase
from tongagents.message.message import (
    ConfigDeserializer,
    Message,
    MessageChunk,
    MessageRole,
    Serializable,
)


class FileMemory(MemoryBase):
    """把对话记忆以 JSONL 追加写入本地文件, 跨进程可恢复.

    与 SimpleMemory 的区别只有一点: 数据落在文件里而不是 self.store 列表里.
    与 PersistenceMemory 的区别: 不需要 SQLAlchemy/数据库, 一个文本文件即可.
    """

    def __init__(
        self,
        path: str | Path,
        agent_id: str = "paper-agent",
        session_id: str = "paper-review",
    ):
        self.path = Path(path)
        self.meta_data = {"agent_id": agent_id, "session_id": session_id}

    # ============================================================
    # 文件 IO (已提供, 不需要修改)
    # ============================================================
    def _append_record(self, record: dict) -> None:
        """把一条记录以 JSONL 追加写入文件."""
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read_records(self) -> list[dict]:
        """读出文件中全部记录 (跳过空行)."""
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    @staticmethod
    def _dump_content(content) -> str:
        """把 chunk 内容序列化成字符串 (已提供的示例).

        Serializable 对象 (如 ChatHistoryUnit) 调用它的 dump();
        普通字符串原样返回.
        """
        if isinstance(content, Serializable):
            return content.dump()
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
        return str(content)

    # ============================================================
    # TODO(1): 写路径 add_chunk
    # ============================================================
    def add_chunk(
        self,
        content,
        role: MessageRole = MessageRole.UNSPECIFIED,
        require_upload: bool = False,
    ) -> None:
        """把一个 chunk 追加写入文件.

        提示:
        1. 组装记录 dict, 至少包含:
             timestamp: get_current_timestamp()
             role:      role.value
             meta_data: dict(self.meta_data)     # agent_id / session_id 靠它过滤
             serial_name: type(content).__name__ # 类型标签! 读取还原全靠它
             content:   self._dump_content(content)
        2. 调用 self._append_record(record)
        """
        # record = {
        #     "timestamp": get_current_timestamp(),
        #     "role": role.value,
        #     "meta_data": dict(self.meta_data),
        #     "serial_name": type(content).__name__,
        #     "content": self._dump_content(content),
        # }
        # self._append_record(record)
        raise NotImplementedError("Lesson 6 TODO(1): 实现 add_chunk")

    # ---- 下面三个写方法是薄封装, 已提供 ----

    def add_chunks(self, chunks: list[MessageChunk], role=MessageRole.UNSPECIFIED):
        for chunk in chunks:
            self.add_chunk(chunk.content, role=role)

    def add_message(self, message: Message):
        for chunk in message.chunks:
            self.add_chunk(chunk.content, role=message.role)

    def add_messages(self, messages: list[Message]):
        for message in messages:
            self.add_message(message)

    # ============================================================
    # TODO(2): 读路径 get_messages
    # ============================================================
    def get_messages(
        self,
        session_id: str | None = None,
        recent_n: int | None = None,
        config: ConfigDeserializer | None = None,
        **kwargs,
    ) -> list[Message]:
        """读回消息列表, 框架恢复上下文全靠它.

        提示 (对照 SQLStoreEngine.read + convert_chunks):
        1. self._read_records() 拿到全部记录;
        2. 按 r["meta_data"]["session_id"] 过滤 — 用 session_id 参数
           (为 None 时用 self.meta_data["session_id"]);
        3. recent_n 不为 None 时只保留最后 recent_n 条 (时间戳升序排好后取尾部);
        4. 还原每条记录为 Message:
             content = (config or {}).get(r["serial_name"], lambda x: x)(r["content"])
           即: config 里有该类型的反序列化器就调用它 (str -> 对象),
               没有就原样返回字符串;
             role 用 MessageRole.value_of(r["role"]) 还原.
        """
        # TODO(2): 删除下面这行, 按上面的提示实现
        raise NotImplementedError("Lesson 6 TODO(2): 实现 get_messages")

    # ============================================================
    # TODO(3): clear 只清理当前 session
    # ============================================================
    def clear(self):
        """清空**当前 session** 的记录, 保留文件中其他 session 的数据.

        提示: 读出全部记录 -> 过滤掉当前 session_id 的 -> 整体重写文件
        (可以先写临时文件再 replace, 避免写一半崩溃丢数据).
        """
        # TODO(3): 删除下面这行, 按上面的提示实现
        raise NotImplementedError("Lesson 6 TODO(3): 实现 clear")
