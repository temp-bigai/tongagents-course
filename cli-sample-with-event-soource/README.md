# cli-sample-with-event-soource

一个**最小可运行**的 Tong-Agent EventSource 教学示例.

跟 `cli-sample/` 配套:
- `cli-sample/` 演示 **Agent + Tools** (LLM 调本地工具)
- `cli-sample-with-event-soource/` 演示 **EventSource + Handler** (定时事件 -> 业务处理)

两者**互补不冲突**: tools/ 是 Agent 工具, event_source/ 是事件源, 都是 Agent 的"输入侧"组件.

---

## 1. 它解决什么问题?

Tong-Agent CLI 在跑 REPL 时, 用户输入是 **拉模式 (pull)**: 用户问一句, Agent 答一句.
但很多场景是 **推模式 (push)**:
- "每隔 30 分钟提醒我检查一下邮箱"
- "收到 GitHub webhook 时自动 review PR"
- "飞书群有新消息时主动响应"
- "cron 每天早上 9 点给我一个简报"

这类场景需要 **EventSource (事件源)**:
- 不依赖用户输入
- 由外部 (timer / webhook / IM) 主动产生 **Event**
- Event 通过 **Runtime** 派发给 **Handler**
- Handler 决定怎么响应 (调 LLM / 写文件 / 发通知)

本示例实现最小版: **TimerEventSource** (每 N 秒触发) + **CliEventHandler** (打印日志).

---

## 2. 架构

```
                ┌──────────────────────────────────────────┐
                │          EventSourceRuntime              │
                │                                          │
 TimerEventSource                │ queue                  │
  - name: sample_timer           │                       │
  - interval: 30s                 ▼                       │
  - max_count: 5         ┌──────────────────┐             │
        │                │ Event dataclass  │             │
        │ start(emit)    │  type=           │             │
        └───────────────▶│  source=         │             │
                         │  payload={...}   │             │
                         │  timestamp=      │             │
                         └────────┬─────────┘             │
                                  │ dispatch_loop         │
                                  ▼                       │
                         ┌──────────────────┐             │
                         │  CliEventHandler │             │
                         │   handle(event)  │             │
                         │   ├─ 打印日志    │             │
                         │   └─ 业务占位    │             │
                         └──────────────────┘             │
                                                          │
 Lifecycle:  start() ──▶ [running] ──▶ stop()             │
──────────────────────────────────────────────────────────
```

关键抽象 (在 `event_source/runtime.py`):

```python
@dataclass
class Event:
    type: str       # 'timer.tick', 'user.message', 'webhook.github' ...
    source: str     # 来源 source 名
    payload: dict   # 自由 dict
    timestamp: str  # ISO-8601
```

---

## 3. 文件结构

```
cli-sample-with-event-soource/
├── README.md                          # 本文件
├── requirements.txt                   # 无外部依赖
└── src/
    ├── main.py                        # CLI 入口 (含信号处理)
    ├── event_source/                  # 事件源 (跟 tools 同级)
    │   ├── __init__.py
    │   ├── runtime.py                 # EventSourceRuntime + Event dataclass
    │   └── timer_source.py            # TimerEventSource
    └── handlers/                      # 处理器 (跟 tools 同级)
        ├── __init__.py
        └── cli_handler.py             # CliEventHandler
```

参考 Tong-Agent 实现 (`Tong-Agent/cli/src/tongagents_cli/event_source/`):
- `runtime.py` ← `tongagents_cli/event_source/runtime.py` (Handler 注册表, 简化版)
- `timer_source.py` ← `tongagents_cli/event_source/handlers/timer.py` (TimerHandler, 简化版)
- `cli_handler.py` ← `tongagents_cli/event_source/handlers/lark_cli.py` (Handler 基类)

**简化点** (本示例**不**包含 Tong-Agent 的):
- ❌ `storage.py` - 持久化配置 (本示例无持久化, 进程内)
- ❌ `event_store.py` - 事件流持久化
- ❌ `daemon.py` - 后台进程 + PID 文件
- ❌ `commands.py` - Click CLI 命令组
- ❌ SDK dispatcher 耦合 - 不触发 LLM, 只派发给 handler
- ❌ cron 表达式 (只支持 interval, 教学够用)

---

## 4. 运行

### 4.1 默认 (每 30 秒触发, 触发 5 次后自动停)

```bash
cd cli-sample-with-event-soource/src
python3 main.py
```

预期输出 (时间戳会变):

```
[10:40:00] INFO  cli-sample-with-event-soource: ============================================================
[10:40:00] INFO  cli-sample-with-event-soource: CLI Sample with EventSource 启动
[10:40:00] INFO  cli-sample-with-event-soource:   interval = 30.0 秒
[10:40:00] INFO  cli-sample-with-event-soource:   max_count = 5
[10:40:00] INFO  cli-sample-with-event-soource:   按 Ctrl+C 提前退出
[10:40:00] INFO  cli-sample-with-event-soource: ============================================================
[10:40:00] INFO  event_source.runtime: Registered source: sample_timer (type=TimerEventSource)
[10:40:00] INFO  event_source.runtime: Registered handler: cli_console (type=CliEventHandler)
[10:40:00] INFO  event_source.runtime: Bound sample_timer -> cli_console
[10:40:00] INFO  event_source.runtime: Dispatcher loop started
[10:40:00] INFO  event_source.timer: [sample_timer] started, interval=30.0s, max_count=5, event_type=timer.tick
[10:40:30] INFO  handler.cli: [cli_console] 收到事件: Event[timer.tick] from sample_timer @ 2026-09-10T10:40:30 payload={'source': 'cli-sample-with-event-soource', 'note': '每 30 秒触发一次', 'tick': 1}
[10:40:30] INFO  handler.cli: [cli_console] [业务] 处理 timer.tick #1 (每 30 秒触发一次)
... (每 30 秒一次, 共 5 次) ...
[10:42:30] INFO  event_source.timer: [sample_timer] reached max_count=5, auto-stopping
[10:42:30] INFO  event_source.runtime: 所有 source 都自然结束, runtime auto-stopping
[10:42:30] INFO  cli-sample-with-event-soource: ============================================================
[10:42:30] INFO  cli-sample-with-event-soource: CLI Sample with EventSource 退出
[10:42:30] INFO  cli-sample-with-event-soource: ============================================================
```

注意: 触发到 `max_count` 后, `TimerEventSource` 自动停. `EventSourceRuntime` 检测到所有 source
都自然结束, 也会自动停 (auto_stop_when_all_sources_finish=True). 程序自然退出.

### 4.2 自定义间隔 (测试用: 每 2 秒, 触发 3 次)

```bash
cd cli-sample-with-event-soource/src
EVENT_INTERVAL_SECONDS=2 EVENT_MAX_COUNT=3 python3 main.py
```

约 6-7 秒后程序自动退出.

### 4.3 提前退出

按 `Ctrl+C` (SIGINT), runtime 优雅停掉所有 source.

---

## 5. 测试

`/tmp/test_run.py` 是 8 秒集成测试: 验证定时器真的触发, handler 真的收到:

```bash
cd cli-sample-with-event-soource/src
python3 /tmp/test_run.py
```

期望看到 3 个 `tick #1`, `tick #2`, `tick #3`.

---

## 6. 扩展方向

如果想接到真实业务:

### 6.1 触发 LLM 处理 (回到 Tong-Agent SDK)

修改 `cli_handler.py::_handle_timer_tick`:

```python
def _handle_timer_tick(self, event):
    prompt = f"[定时触发 #{event.payload['tick']}] 请检查邮箱, 给我简报."
    actions = self._agent.step(LLMInputEvent(input=[UserPromptMessage(prompt)]))
    # 处理 actions ...
```

### 6.2 加更多事件源

复制 `timer_source.py` 模式, 实现:

- `webhook_source.py` - 监听 HTTP POST
- `fs_watch_source.py` - watchdog 监听文件变化
- `im_source.py` - 飞书/钉钉消息流

### 6.3 多 handler 扇出

一个 source 绑多个 handler (例如: timer 同时触发 CLI 打印 + 写日志文件 + 调 Agent):

```python
runtime.bind(timer_es, cli_handler)
runtime.bind(timer_es, file_handler)
runtime.bind(timer_es, agent_handler)
```

---

## 7. 跟 Tong-Agent 的对应关系

| 本示例 | Tong-Agent `tongagents_cli.event_source` |
|---|---|
| `EventSourceRuntime` | `runtime.EventSourceRuntime` (单例) |
| `Event` dataclass | `event_store.EventSourceEvent` |
| `TimerEventSource` | `handlers.TimerHandler` (BaseHandler 子类) |
| `CliEventHandler` | `handlers.LarkCliHandler` |
| `add_source` / `add_handler` / `bind` | `storage + runtime.start(record)` |
| ❌ 无 storage | `storage.EventSourceStorage` (JSON 持久化) |
| ❌ 无 daemon | `daemon.DaemonManager` (double-fork 后台进程) |
| ❌ 无 SDK dispatcher | `daemon_entry._dispatch_to_agent` |
| ❌ 无 CLI commands | `commands.event_source_group` (Click) |

教学示例保留核心抽象 (Source / Event / Runtime / Handler), 砍掉所有持久化 / 后台 / CLI 框架,
让初学者能 5 分钟看完 200 行代码搞懂 eventsource 是什么.
