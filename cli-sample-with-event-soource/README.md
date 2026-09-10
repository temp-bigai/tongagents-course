# CLI Sample with EventSource + Agent

最小可运行的 **Tong-Agent EventSource + Agent 集成** 教学示例 (Task #3468 v2).

跟 `cli-sample/` 互补:
- `cli-sample/`: **Agent + Tools** (LLM 调用本地工具)
- `cli-sample-with-event-soource/`: **EventSource + Agent** (定时触发 → agent 处理 → 工具调用)

---

## 🎯 目标

按用户飞书反馈 (Task #3468): 之前 ES sample 只"打印日志"不够, 需要:

1. ✅ ES 触发后, 把 event 封装成 **user input**
2. ✅ 走 Tong-Agent 的 agent 处理流程 (类似 `cli.act` 把 query 喂给 workflow.stream)
3. ✅ agent 用各种 tool 处理 event (bash / read_file / write_file / list_files)
4. ✅ 集成之前 cli-sample 的逻辑 (4 个 tool 跟 cli-sample/tools/ 同名同功能)

---

## 流程 (v2 AgentHandler)

```
TimerEventSource (每 N 秒触发)
   ↓ emit(Event)
EventSourceRuntime.queue
   ↓ dispatch
AgentHandler.handle(event)
   ├─ _event_to_query(event)         # 把 Event 包装成 user query
   │                                  # 类似 Tong-Agent lark_cli 提取 message 字段
   ↓ user_query
_mini_agent_loop(user_query)         # 类似 Tong-Agent act(query) → workflow.stream(query)
   ├─ mock LLM 决策                   # 教学版: 用确定性 plan 替代 LLM
   ├─ bash(args)         # Tool #1: subprocess.run + shlex.split
   ├─ write_file(args)   # Tool #2: 追加写入 /tmp/es_agent_log.txt
   └─ list_files(args)   # Tool #3: glob 列出 *.py 文件
   ↓ tool 结果
写入历史 + 控制台日志
```

---

## 文件结构

```
cli-sample-with-event-soource/
├── README.md                          # 本文件
├── test_run.py                        # 集成测试 (v2 AgentHandler)
├── src/
│   ├── main.py                        # CLI 入口 (默认 v2 AgentHandler)
│   ├── event_source/
│   │   ├── __init__.py
│   │   ├── runtime.py                 # EventSourceRuntime (Source → queue → Handler)
│   │   └── timer_source.py            # TimerEventSource (固定间隔 emit)
│   └── handlers/
│       ├── __init__.py
│       ├── cli_handler.py             # v1 (保留): 只打印
│       └── agent_handler.py           # v2 (新): event → user query → mini agent + tools
└── pyproject.toml                     # (如果有, 跟 cli-sample 同)
```

---

## 运行

### 默认 (v2 AgentHandler)

```bash
cd cli-sample-with-event-soource/src
python3 main.py
```

预期:
- 每 `EVENT_INTERVAL_SECONDS` 秒 (默认 30) 触发一次 timer tick
- AgentHandler 收到 Event → 包装 user query → 调 mini agent loop
- 每次触发调 3 个 tool: `bash` (date -u) + `write_file` (追加日志) + `list_files`
- 日志写入 `/tmp/es_agent_log.txt` (可自定义 `EVENT_LOG_FILE`)
- `EVENT_MAX_COUNT` 次后自动停 (默认 5)

### 快速测试

```bash
EVENT_INTERVAL_SECONDS=1 EVENT_MAX_COUNT=2 python3 main.py
# 2 秒内 2 次 tick, 每个 tick 调 3 个 tool, 日志文件有 2 条 [event]
```

### 切换回 v1 (只打印)

```bash
EVENT_HANDLER=cli EVENT_INTERVAL_SECONDS=1 EVENT_MAX_COUNT=2 python3 main.py
```

### 集成测试

```bash
cd cli-sample-with-event-soource
python3 test_run.py
```

预期 5 项断言全部通过:
1. 日志文件含 3 条 `[event]` 记录
2. `AgentHandler.history` 有 3 条 user + 9 条 tool (3 events × 3 tools)
3. 每个 event 都用了 bash + write_file + list_files
4. 耗时 5-12 秒
5. 所有非主线程退出

---

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `EVENT_INTERVAL_SECONDS` | `30` | 定时间隔 (秒) |
| `EVENT_MAX_COUNT` | `5` | 最大触发次数 (None = 无限) |
| `EVENT_LOG_FILE` | `/tmp/es_agent_log.txt` | AgentHandler 写入的日志 |
| `EVENT_HANDLER` | `agent` | `agent` (v2) 或 `cli` (v1) |

---

## 与 Tong-Agent 对应

| 本示例 | Tong-Agent |
|---|---|
| `TimerEventSource` | `tongagents_cli.event_source.handlers.TimerHandler` |
| `AgentHandler.handle(event)` | `cli.act(query)` 入口 |
| `_event_to_query(event)` | (lark_cli 提取 message 字段) |
| `_mini_agent_loop(query)` | `workflow.stream(query)` |
| `bash` / `read_file` / `write_file` / `list_files` | `tongagents_cli.default_agent.tools.{Bash,ReadFile,WriteFile,Glob}Tool` |
| mock LLM 决策 | Tong-Agent: 真实 LLM 输出 tool_calls |

---

## 简化点 (相对 Tong-Agent)

| 维度 | 本示例 | Tong-Agent |
|---|---|---|
| LLM | 无 (mock 决策) | 真实 (OpenAI-compatible) |
| 持久化 | 无 (进程内 queue) | storage + daemon |
| Tools | 4 个本地简化版 | 完整 SDK 工具集 |
| Event 派发 | 单进程 dispatcher | SDK EventDispatcher + 持久化 |
| Session | 无 | SessionManager (多轮对话) |

教学示例保留核心抽象 (Source / Runtime / Handler + Tools), 省略生产级特性.

---

## 设计动机

- **为什么 mock LLM**: 教学示例不绑 OPENAI_API_KEY (LLM 需要). 但工具必须真实 (否则演示 agent + tool 集成没意义).
- **为什么 4 个 tools**: 跟 `cli-sample/tools/` 同名, 让用户能对比"纯工具" vs "工具被 agent 调"两种使用方式.
- **为什么保留 v1 CliEventHandler**: 教学分阶段: v1 只打印, v2 跑 agent 流程. 通过 `EVENT_HANDLER=cli/agent` 切换.

---

## 任务来源

- Task #3467 (v1): 加 cli-sample-with-event-soource folder, 演示 EventSource + Handler
- **Task #3468 (v2, 本次)**: ES 触发后走 agent + tool 流程, 集成 cli sample 逻辑

用户原话: "在 Tong-Agent 的 cli 里面, 是将 event 封装下当成 user input 输入的, 然后就走 agent 处理用户 query 的 llm 流程的, 我希望这个 es sample 也是这样, 这样才能集成之前 cli sample 的逻辑哈, 效果就是定时事件发出之后, agent 利用各种 tool 来处理这个 event 哈"