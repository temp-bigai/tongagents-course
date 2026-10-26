# Lesson 6 作业：给论文综述 Agent 装上记忆（自己实现 FileMemory）

Lesson 5 结束时，我们的 Agent 已经会检索 arXiv 并生成综述，但它是"失忆"的：`StatelessReactAgent` 每次 `step()` 前都会清空内部历史，`dep_context` 里就算传了 memory 也没有任何代码消费它——重启进程、甚至只是第二轮追问"刚才那篇综述"，Agent 都一无所知。

本节课自己实现一个持久化记忆 `FileMemory`：参考 SDK 的 `MemoryBase` 接口与 `SimpleMemory`（内存版），把对话以 JSONL 写入本地文件，再接入 SDK 自带的 `ReActAgentWithMemory`，让综述 Agent **重启后仍记得上一篇综述**。

## 作业概览

- **作业目标**：参考 `MemoryBase` 与 `SimpleMemory`，自行实现持久化记忆 `FileMemory`，接入 `ReActAgentWithMemory`，使综述 Agent 重启后仍记得上一轮综述。
- **核心任务**：实现 `FileMemory(MemoryBase)` 全部抽象方法，记忆以 JSONL 写入本地文件（记录含时间戳、session、内容及**类型标签**）；`get_messages` 支持按 session 过滤、`recent_n` 截断，并按类型标签还原为原对象；经 `LLMRunContext(memory=FileMemory)` 注入 `ReActAgentWithMemory`，`search_arxiv` 沿用 Lesson 5。
- **关键要求**：读取须还原为原对象（否则框架抛 `ValueError`）；第 2 轮回答必须来自记忆文件，不得凭模型记忆复述；验收须重启进程，提交记忆文件、第 2 轮上下文与工具调用记录。
- **最终效果**：第 1 轮 主题 → `search_arxiv` → 中文综述 → 写入 FileMemory 退出；第 2 轮（重启、同 session）追问 → 恢复上轮综述 → 不再检索 → 基于综述回答并标注来源。

## 记忆是怎么和 Agent 接起来的

SDK 里 memory 与 Agent 的接线只有一处，而且是**注入**的，不是 Agent 自己创建的：

```text
调用方:  memory = FileMemory(...)              # 你实现的后端
         dep_context = LLMRunContext(memory=memory)   # 只装 memory 的壳
                │
ReActAgentWithMemory(dep_context=dep_context, ...)
                │
                └─ 构造时把 dep_context.memory 交给 SlidingWindowRAGContextWindowManager:
                     · 初始化读: memory.get_messages(recent_n, config=...)
                       把最近几轮 ChatHistoryUnit 回填上下文   ← 重启恢复发生在这里
                     · 每轮终态写: memory.add_chunk(ChatHistoryUnit 对象)
                       对话单元完成时落库                     ← 综述在这里入记忆
```

两条契约红线（`check_memory.py` 用于校验测试是否正确）：

1. **写入要打类型标签**：chunk 内容是对象（如 `ChatHistoryUnit`），落盘时存 `type(content).__name__` + `content.dump()` 字符串；
2. **读取要还原对象**：框架调用 `get_messages` 时会传入反序列化器 `config`（`{"ChatHistoryUnit": ChatHistoryUnit.load}`），你必须用它把字符串还原回对象——还原失败时框架直接抛 `ValueError: Invalid message type`。

## 脚手架

lesson6/ 已提供（环境方式与 lesson1 / cli-sample 相同：本地 wheel，不走 nexus）：

```text
lesson6/
├── README.md               # 本文件
├── pyproject.toml          # 自身依赖 (python-dotenv); tongagents 从 ../wheels/ 安装
├── reference/              # SDK 源码节选 (只读) — 为什么: 见 reference/README.md
├── memory/
│   ├── __init__.py
│   └── file_memory.py      # TODO(1)(2)(3): add_chunk / get_messages / clear
├── check_memory.py         # 8 项自测, 不需要 LLM 和网络
└── cli_memory_sample.py    # TODO(4)(5)(6): 记忆构造 / 注入 / 多轮 prompt 规则
```

文件 IO、序列化示例（`_dump_content`）、薄封装方法（`add_message` 等）已给出；需要你完成的只有 TODO 标记处，每个 TODO 的注释里都有分步提示。

## 第 0 步：确认起点

- 已完成 Lesson 5：`cli-sample/tools/` 里有 `arxiv_search_tool.py`，且 `search_arxiv` 已注册（`tools/__init__.py` 的 `_DEFAULT_TOOL_CLASSES`）；
- 仓库根目录 `wheels/` 已放入维护者提供的 tongagents wheel（流程见 `lesson1/INSTALL.md`，本课不需要 tongagents_cli）；
- 初始化本课环境（首次使用执行一次，与 lesson1 同一套流程）：

```bash
cd lesson6
python3 -m venv .venv && source .venv/bin/activate
pip install ../wheels/tongagents-*.whl   # 先装 wheel (SDK)
pip install -e .                         # 再装本课自身依赖 (python-dotenv)
```

> 装了 uv 的同学可以等价使用：`uv venv && source .venv/bin/activate`，
> `uv pip install ../wheels/tongagents-*.whl && uv pip install -e .`，
> 运行时用 `python ...`（已激活）或 `uv run --no-sync python ...`（未激活）。
> 顺序很重要：先 wheel 再 `-e .`，否则 pip 会去公网找 tongagents 而失败。

- `.env` 沿用 cli-sample 的那份（`cli_memory_sample.py` 会自动加载 `../cli-sample/.env`）。

## 第 1 步：读参考代码（reference/）
`reference/` 附上了本课相关的 SDK 源文件节选（对照表见 `reference/README.md`），
按顺序读：

1. `reference/memory.py` — `MemoryBase` 六个抽象方法（你要实现的接口）+ `SimpleMemory`（一个 `list` 存一切，进程退出即丢——你的对照组）；
2. `reference/message.py` — `Message` / `MessageChunk` / `Serializable`（dump/load 协议）/ `ConfigDeserializer`（按类型名还原对象的机制）；
3. `reference/context_window_base.py` — `ChatHistoryUnit`（一轮对话的状态机，落库的最小单位）；
4. `reference/sliding_window_rag_context_window_manager.py` — **"甲方"如何使用你的 memory**：`_get_recent_chat_units()`（初始化恢复，类型不对抛 `ValueError`）与 `_save_chat_unit_to_memory()`（终态落库）；
5. `reference/sql_engine.py` — **参考答案**：`_insert()` 写入时记 `serial_name`，`convert_chunks()` 读取时用 `config` 还原；你的 FileMemory 就是它的 JSONL 文件版。

## 第 2 步：实现 TODO(1) add_chunk

打开 `memory/file_memory.py`，按注释提示组装记录 dict 并调用 `_append_record`。完成后先手动验证：

```bash
cd lesson6 && python -c "
from tongagents.agents.context_window.base import ChatHistoryUnit
from tongagents.agents.llm.messages import UserPromptMessage, ModelOutputMessage, ModelTextMessage
from memory import FileMemory
u = ChatHistoryUnit(); u.add_message(UserPromptMessage(content='Q'))
u.add_message(ModelOutputMessage(model_text_message=ModelTextMessage(content='综述A')))
FileMemory('/tmp/t.jsonl').add_chunk(u)
print(open('/tmp/t.jsonl').read())
"
```

输出应是一行 JSON，含 `"serial_name": "ChatHistoryUnit"`。

## 第 3 步：实现 TODO(2) get_messages

按注释三小步：按 session 过滤 → `recent_n` 取尾部 → 用 `config` 还原对象。这是全题的核心，对照 `reference/sql_engine.py` 的 `read()` + `convert_chunks()` 写。

## 第 4 步：实现 TODO(3) clear

只清当前 session 的记录（文件里可能混存多个 session，按 `meta_data` 过滤后重写文件），不得删掉别人的数据。

## 第 5 步：跑自测

```bash
cd lesson6 && python check_memory.py
```

8 项全过即达到框架契约，其中 `test_08` 是框架级终验：用真实的 `SlidingWindowRAGContextWindowManager` 走一遍"落库 → 新实例恢复 → 上下文里有上一篇综述"，全程不需要 LLM。建议再做一件事：故意把 `get_messages` 改成忽略 `config`，重跑自测观察哪几项挂掉——体会类型还原为什么是红线。

## 第 6 步：完成 CLI 接线 TODO(4)(5)(6)

`cli_memory_sample.py` 里只剩三处：

- TODO(4) `build_memory()`：用文件顶部的 `MEMORY_FILE / AGENT_ID / SESSION_ID` 构造 FileMemory，一行；
- TODO(6) `CliMemoryAgent.__init__`：`dep_context = LLMRunContext(memory=memory)`（注意 `dep_context` 不能是 None，agent 内部直接读 `.memory`）；
- TODO(5) `_SYSTEM_PROMPT`：把注释里的三条多轮规则写成正式 prompt（已有综述直接引用不重复检索 / 注明依据来源 / 新方向才再检索）。

运行：

```bash
cd lesson6 && python cli_memory_sample.py
```

启动横幅会显示记忆文件路径与"已恢复 N 轮对话"——第二次启动时 N 应大于 0。

## 第 7 步：跨进程验收

```text
第 1 次运行:
>>> 检索 LLM Agent memory 相关论文，并生成中文综述
    （观察: 调用 search_arxiv → 输出综述 → 退出）
>>> exit

第 2 次运行 (重启后):
>>> 上一篇综述里的方法分类，再展开讲讲
    （期望: 不再调用 search_arxiv, 回答引用上一篇综述并标注来源）
>>> 在上一篇基础上补充 2024 年之后的工作
    （期望: 仅对新方向补充检索）
```

再做两组对照，确认"记得"确实来自你的文件而不是巧合：

- 把 `SESSION_ID` 换成新值重跑第 2 轮 → 应退化为重新检索（记忆按 session 隔离）；
- 把 `build_memory()` 临时换成 `SimpleMemory()` 重启重跑 → 应同样失忆（不落盘）。

## 验收标准

- `FileMemory` 完整实现 `MemoryBase` 全部抽象方法，`check_memory.py` 8 项全部通过；
- JSONL 记录含类型标签；`get_messages` 传入 `config` 时还原为原对象；
- `clear()` 只清当前 session，文件中其他 session 记录保留；
- 第 2 轮（重启进程、同 session）能引用上一篇综述回答，且未重复调用 `search_arxiv`（新方向除外）；
- 两组对照（换 session / SimpleMemory）均表现为失忆或退化重检；
- 提交：`memory/file_memory.py`、`cli_memory_sample.py` 的修改，记忆文件 `paper_memory.jsonl` 节选，以及第 1、2 轮的对话截图或记录。

## 延伸思考（选做）

- 把 `max_history_len` 调成 1 和 10 各试一次，第 2 轮的回答有什么差别？滑窗滚出后丢了什么？
- 打开 `tool_call_memory=True` 再跑第 2 轮：arXiv 原始结果也进入上下文后，追问"某篇论文的作者"能答上吗？代价是什么（上下文长度）？
- 你的 JSONL 版与 SDK 的 `SQLStoreEngine` 相比，各适合什么规模？什么时候该换数据库？
