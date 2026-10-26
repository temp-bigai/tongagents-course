# reference/ — SDK 源码节选（只读，供阅读）

**为什么要复制出来**：课程环境里 `tongagents` 以 wheel 安装，模块是 Cython 编译后的
`.so` 二进制（可以在 `.venv/lib/python3.12/site-packages/tongagents/` 里看一眼，
全是 `*.so`）——直接翻 site-packages **读不到源码**，所以这里附上与本课相关的
SDK 源文件节选。以环境实际安装的版本为准，本目录只作阅读参考，**不要修改、
不要 import**（部分文件依赖 sqlalchemy 等，仅用于阅读）。

## 阅读顺序与文件对照

| 顺序 | 本目录文件 | SDK 内原始路径 | 读什么 |
|---|---|---|---|
| 1 | `memory.py` | `tongagents/memory/memory.py` | `MemoryBase` 六个抽象方法（你要实现的接口）+ `SimpleMemory`（内存版参考，一个 `list` 存一切） |
| 2 | `message.py` | `tongagents/message/message.py` | `Message` / `MessageChunk` / `MessageRole` / `Serializable`（dump/load 协议）/ `ConfigDeserializer`（按类型名还原对象的机制） |
| 3 | `context_window_base.py` | `tongagents/agents/context_window/base.py` | `ChatHistoryUnit`（一轮对话的状态机，落库的最小单位）+ `ContextWindowManager` 接口 |
| 4 | `sliding_window_rag_context_window_manager.py` | `tongagents/agents/context_window/sliding_window_rag_context_window_manager.py` | **"甲方"如何使用你的 memory**：初始化读（`_get_recent_chat_units`，还原失败抛 `ValueError`）与终态写（`_save_chat_unit_to_memory`） |
| 5 | `sql_engine.py` | `tongagents/memory/sql_engine.py` | **参考答案**：`_insert()` 写入时记 `serial_name`，`convert_chunks()` 读取时用 `config` 还原——你的 FileMemory 就是它的 JSONL 文件版 |

建议对照方式：左边开你自己的 `memory/file_memory.py`，右边开 `sql_engine.py`，
找 `_insert` / `convert_chunks` 与你 `add_chunk` / `get_messages` 的对应关系。
