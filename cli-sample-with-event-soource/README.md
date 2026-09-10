# CLI Sample with EventSource + Agent (v4)

最小可运行的 **Tong-Agent EventSource + Agent 集成** 教学示例 (Task #3470 v4).

跟 `cli-sample/` 互补:
- `cli-sample/`: **Agent + Tools** (LLM 调用本地工具)
- `cli-sample-with-event-soource/`: **EventSource + Agent** (定时触发 → agent 处理 → 工具调用)

---

## 🎯 v4 设计目标 (Task #3470)

按用户飞书反馈 (Task #3470): v3 不符合预期, **handler 重复造轮子**, 应该:

1. ✅ **单 handler** — 去掉 `CliEventHandler / cli_observer`, 只保留 `AgentHandler`
2. ✅ **复用 cli-sample 的"等用户 input + 输出 agent response"循环** —
   v3 AgentHandler 自己实现 `_mini_agent_loop / _call_real_llm_loop / _execute_tool`,
   v4 完全删掉, 直接复用 `cli-sample/cli_sample.py:main()` 的循环结构
3. ✅ **ES event 封装成 user input, 注入同一个循环** — Event 走和 user input 完全一样的路径
4. ✅ **标明复用 cli-sample 逻辑, 只新增 ES 机制**

---

## 流程 (v4)

```
┌──────────────────────────────────────────────────────────────────────┐
│ 主线程: 复用 cli-sample 的 REPL 循环 (跟 cli_sample.py:main() 一致)  │
│   while True:                                                         │
│       user_input = input_queue.get()       # user 或 ES 注入          │
│       if user_input in ('exit','quit','q'): break                     │
│       response = agent.step(user_input)     # SDK StatelessReactAgent│
│       print(response)                                                 │
└──────────────────────────────────────────────────────────────────────┘
                              ↑                                ↓
                  input_queue (queue.Queue)             agent.step() (SDK)
                              ↑
                  ES dispatcher thread (后台)
                              ↑
                  runtime.get_event() (auto_dispatch=False)
                              ↑
                  runtime._queue
                              ↑
                  TimerEventSource (后台线程)
```

**复用 vs 新增**:
| 来自 cli-sample (复用) | 本文件 (新增) |
|---|---|
| `agent.step()` 调用结构 | `input_queue` (合并 user + ES 事件) |
| REPL 循环: `input → step → print` | `event_to_user_input()` 转换 |
| 6 个工具 (`bash / read_file / ...`) | ES dispatcher 后台线程 |
| `StatelessReactAgent` 构造 | `runtime.auto_dispatch=False` 模式 |

---

## 文件结构 (v4)

```
cli-sample-with-event-soource/
├── README.md                          # 本文件
├── test_run.py                        # 集成测试 (v4: --mock-llm / 默认)
├── src/
│   ├── main.py                        # CLI 入口 (复用 cli-sample 循环 + ES dispatcher)
│   ├── event_source/
│   │   ├── __init__.py
│   │   ├── runtime.py                 # EventSourceRuntime (新: auto_dispatch 模式)
│   │   └── timer_source.py            # TimerEventSource (固定间隔 emit)
│   └── handlers/
│       ├── __init__.py                # 只导出 AgentHandler
│       └── agent_handler.py           # 单 handler (复用 cli-sample agent 模式)
└── requirements.txt
```

注意: v4 **删除了** `cli_handler.py` (CliEventHandler / cli_observer 不再存在).

---

## 运行

### 默认 (有 OPENAI_API_KEY + OPENAI_MODEL 走真 LLM, 否则报错走不通)

```bash
cd cli-sample-with-event-soource/src
python3 main.py
```

预期:
- 后台启动 `TimerEventSource` (默认每 30 秒触发, 最多 5 次)
- ES event 通过 dispatcher 转 user input, 推到 `input_queue`
- 主线程从 `input_queue` 拿 item, 走 cli-sample 一样的 `agent.step(user_input) → print(response)`
- 输入 `exit` / `quit` / `q` 退出

### 真 LLM 跑法 (推荐)

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.minimaxi.com/v1"
export OPENAI_MODEL="MiniMax-M2"

cd cli-sample-with-event-soource/src
python3 main.py
```

### 快速测试 (短间隔)

```bash
EVENT_INTERVAL_SECONDS=1 EVENT_MAX_COUNT=2 python3 main.py
```

### 集成测试

```bash
cd cli-sample-with-event-soource
python3 test_run.py                    # 默认: 真调 LLM (如果有 env)
python3 test_run.py --mock-llm         # 跳过 LLM 调用, 只验证 ES 注入 + 循环
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | (无) | LLM key |
| `OPENAI_BASE_URL` | (无) | OpenAI 兼容端点 URL |
| `OPENAI_MODEL` | (无) | 模型名 |
| `EVENT_INTERVAL_SECONDS` | `30` | 定时间隔 (秒) |
| `EVENT_MAX_COUNT` | `5` | 最大触发次数 |

---

## v3 → v4 关键变化

| 维度 | v3 (Task #3469) | v4 (Task #3470) |
|---|---|---|
| Handler 数 | 2 (AgentHandler + CliEventHandler) | **1** (AgentHandler) |
| 循环逻辑 | AgentHandler 内实现 `_mini_agent_loop` | **复用 cli-sample 的 REPL** |
| Event 处理路径 | runtime dispatcher → `handler.handle(event)` → 内部 mini loop | runtime `auto_dispatch=False` → ES dispatcher → 转 user input → input_queue → cli-sample 循环 |
| Agent 构造 | AgentHandler 内置 `StatelessReactAgent` | AgentHandler 提供 `.agent`, 跟 cli-sample 同构造 |
| Mock fallback | AgentHandler `_mock_llm_loop` + 简易 tool | **删除** — cli-sample 本身只跑真 LLM, 没 mock |
| 用户输入 | 不支持 (只有 ES 触发) | input_queue 合并 user + ES (跟 cli-sample 一样) |
| `Runtime` 配置 | `add_handler` + `bind` | **`auto_dispatch=False`** (外部消费) |

---

## 与 Tong-Agent / cli-sample 对应

| 本示例 (v4) | cli-sample/cli_sample.py | Tong-Agent |
|---|---|---|
| `AgentHandler.agent` | `CliSampleAgent` (内部 `StatelessReactAgent`) | `tongagents_cli` agent |
| `run_cli_loop()` | `main()` (REPL) | `cli` REPL |
| `event_to_user_input()` | — (没有 ES) | (lark_cli 提取 message 字段) |
| `make_es_dispatcher()` | — | (SDK dispatcher 走 EventSource) |
| `TimerEventSource` | — | `tongagents_cli.event_source.handlers.TimerHandler` |
| 6 个 tool | 同 | `tongagents_cli.default_agent.tools.*` |

---

## 设计动机

- **为什么 v4 删掉 mini loop**: 用户飞书原话:
  > "handler 里面就保留使用到的 handler 就好, 一个就行, 另外需要用
  > cli-sample 里面的命令行中的等待用户 input 和输出 agent response 的循环逻辑"

  v3 的 `_mini_agent_loop` / `_call_real_llm_loop` / `_execute_tool` 是重复造轮子
  (cli-sample 已经有完整 REPL). v4 完全复用 cli-sample 的循环, AgentHandler
  只做 "提供 agent" 这一件事.

- **为什么 `auto_dispatch=False`**: v3 让 runtime dispatcher 直接调 `handler.handle(event)`,
  但 v4 我们要把 event 转 user input 注入到 REPL — 需要外部消费 queue.
  所以给 `EventSourceRuntime` 加了 `auto_dispatch` 参数 (默认 True 兼容 v3).

- **为什么删除 CliEventHandler**: 用户原话 "handler 里面就保留使用到的 handler 就好,
  一个就行". v3 的 CliEventHandler 只做 console 打印, 跟"等 user input + 输出 agent
  response"的主循环无关, 删掉.
