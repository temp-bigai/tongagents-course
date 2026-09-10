# CLI Sample with EventSource + Agent

最小可运行的 **Tong-Agent EventSource + Agent 集成** 教学示例 (Task #3469 v3).

跟 `cli-sample/` 互补:
- `cli-sample/`: **Agent + Tools** (LLM 调用本地工具)
- `cli-sample-with-event-soource/`: **EventSource + Agent** (定时触发 → agent 处理 → 工具调用)

---

## 🎯 目标

按用户飞书反馈 (Task #3469): v2 是 mock LLM 决策, 不是真调. 需要:

1. ✅ ES 触发后, 把 event 封装成 **user input**
2. ✅ 走 Tong-Agent 的 agent 处理流程 (类似 `cli.act` 把 query 喂给 workflow.stream)
3. ✅ **真调 LLM** (跟 cli-sample/cli_sample.py 一样, 用 TongAgent SDK StatelessReactAgent)
4. ✅ agent 用 6 个真实 tool 处理 event (read_file / write_file / edit_file / bash / glob / grep)

---

## 流程 (v3 真 LLM)

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
   ├─ 走真 LLM (TongAgent SDK)       # 有 OPENAI_API_KEY + OPENAI_MODEL + tongagents SDK 时
   │    ├─ StatelessReactAgent.step()  # SDK 内部: client.chat.completions.create(...)
   │    ├─ SDK 自动 tool dispatch     # 6 个 SDK tool (bash/read_file/write_file/...)
   │    └─ SDK 自动 tool result 回传 LLM, 直到 is_final_response=True
   └─ fallback 到 mock (v2 行为)     # 缺任一 env / SDK 时, 跟 v2 一样调 3 个简易 tool
   ↓ tool 结果
写入历史 + 控制台日志 + /tmp/es_agent_log.txt
```

---

## 文件结构

```
cli-sample-with-event-soource/
├── README.md                          # 本文件
├── test_run.py                        # 集成测试 (v3: --mock / --real / auto)
├── src/
│   ├── main.py                        # CLI 入口 (默认 AgentHandler)
│   ├── event_source/
│   │   ├── __init__.py
│   │   ├── runtime.py                 # EventSourceRuntime (Source → queue → Handler)
│   │   └── timer_source.py            # TimerEventSource (固定间隔 emit)
│   └── handlers/
│       ├── __init__.py
│       ├── cli_handler.py             # v1 (保留): 只打印
│       └── agent_handler.py           # v3 (新): event → user query → 真 LLM (SDK) + tools
└── requirements.txt                   # openai>=1.0.0 (TongAgent SDK 已依赖)
```

---

## 运行

### 默认 (自动检测: 有 LLM env 走真 LLM, 否则 mock)

```bash
cd cli-sample-with-event-soource/src
python3 main.py
```

预期:
- 每 `EVENT_INTERVAL_SECONDS` 秒 (默认 30) 触发一次 timer tick
- AgentHandler 收到 Event → 包装 user query → 调 mini agent loop
- **有 OPENAI_API_KEY + OPENAI_MODEL**: 真调 TongAgent SDK StatelessReactAgent (6 个 tool)
- **无 env**: fallback 到 mock (3 个 tool 确定性 plan)
- 日志写入 `/tmp/es_agent_log.txt` (可自定义 `EVENT_LOG_FILE`)
- `EVENT_MAX_COUNT` 次后自动停 (默认 5)

### 真 LLM 跑法 (推荐)

```bash
export OPENAI_API_KEY="sk-..."        # LLM key
export OPENAI_BASE_URL="https://api.minimaxi.com/v1"   # OpenAI 兼容端点 (可选)
export OPENAI_MODEL="MiniMax-M2"            # 模型名

cd cli-sample-with-event-soource/src
python3 main.py
```

每次 tick 会真调 LLM, 由 LLM 决策调哪些 tool, SDK 自动 dispatch + 结果回传.

### 快速测试

```bash
EVENT_INTERVAL_SECONDS=1 EVENT_MAX_COUNT=2 python3 main.py
```

### 切换回 v1 (只打印)

```bash
EVENT_HANDLER=cli EVENT_INTERVAL_SECONDS=1 EVENT_MAX_COUNT=2 python3 main.py
```

### 集成测试

```bash
cd cli-sample-with-event-soource
python3 test_run.py                       # auto: 有 env 走真 LLM, 否则 mock
python3 test_run.py --mock                # 强制 mock 路径
python3 test_run.py --real                # 强制真 LLM 路径 (没 env 会退出码 2)
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | (无) | LLM key (真 LLM 路径需要) |
| `OPENAI_BASE_URL` | (无) | OpenAI 兼容端点 URL |
| `OPENAI_MODEL` | (无) | 模型名 (真 LLM 路径需要) |
| `EVENT_INTERVAL_SECONDS` | `30` | 定时间隔 (秒) |
| `EVENT_MAX_COUNT` | `5` | 最大触发次数 |
| `EVENT_LOG_FILE` | `/tmp/es_agent_log.txt` | AgentHandler 写入的日志 |
| `EVENT_HANDLER` | `agent` | `agent` (v3) 或 `cli` (v1) |

---

## v2 → v3 关键变化

| 维度 | v2 (mock LLM) | v3 (真 LLM via SDK) |
|---|---|---|
| LLM 调用 | 确定性 plan (3 个 tool) | TongAgent SDK → `client.chat.completions.create()` |
| 工具集 | 4 个简易版 (本地 callable) | 6 个 SDK Tool (从 cli-sample/tools/ 注册) |
| Tool dispatch | 自己写循环 | SDK 内部自动 (含多轮 tool 调用 + 回传) |
| History | 自己 append mock tool result | SDK actions → TextAction (含 is_final_response 标记) |
| Fallback | 无 | 缺 OPENAI_API_KEY / OPENAI_MODEL / tongagents → 自动 mock |
| 测试 | 3 ticks × 3 tools = 9 tool records | 真 LLM: 3 ticks × N actions (N 由 LLM 决定) |

---

## 与 Tong-Agent 对应

| 本示例 | Tong-Agent |
|---|---|
| `TimerEventSource` | `tongagents_cli.event_source.handlers.TimerHandler` |
| `AgentHandler.handle(event)` | `cli.act(query)` 入口 |
| `_event_to_query(event)` | (lark_cli 提取 message 字段) |
| `_mini_agent_loop(query)` | `workflow.stream(query)` |
| `_call_real_llm_loop` 内部 `StatelessReactAgent.step()` | `StatelessReactAgent.step()` (跟 cli-sample 一致) |
| `bash` / `read_file` / `write_file` / ... (6 个 SDK Tool) | `tongagents_cli.default_agent.tools.{Bash,ReadFile,WriteFile,...}Tool` |
| 真 LLM (OpenAI-compatible API) | Tong-Agent: 同 |

---

## 设计动机

- **为什么 v3 改成真 LLM**: 用户飞书反馈 "真的调通 llm, 可以看看之前跑 cli sample 的任务它也是真实的调通 llm 的呀". v2 mock 决策虽然能演示 agent 框架, 但跟 Tong-Agent 真实用法脱节. v3 用 TongAgent SDK 跑真 LLM, 跟 cli-sample/cli_sample.py 一致.
- **为什么 fallback mock**: 真 LLM 需要 API key, 但教学示例要能"零配置跑起来". 检测 OPENAI_API_KEY + OPENAI_MODEL, 缺一就 fallback mock, 让测试 / 演示都能跑.
- **为什么 6 个 tool**: 跟 `cli-sample/tools/` 复用, 避免重复实现. AgentHandler 初始化时自动注册到 tongagents ToolManager.

---

## 任务来源

- Task #3467 (v1): 加 cli-sample-with-event-soource folder, 演示 EventSource + Handler
- Task #3468 (v2): ES 触发后走 agent + tool 流程, 集成 cli sample 逻辑 (mock LLM)
- **Task #3469 (v3, 本次)**: 把 v2 的 mock LLM 改为真 LLM (TongAgent SDK StatelessReactAgent, 跟 cli-sample 一致)