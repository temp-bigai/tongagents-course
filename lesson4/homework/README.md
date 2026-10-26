# Lesson 4 课后作业：手写 ReAct 循环的本地文件 CLI Agent

`cli-sample` 把 ReAct 循环整个委托给了 SDK 的 `StatelessReactAgent.step()`——模型调用、工具调度、结果回填全是黑盒。本作业把它**白盒重写**：仿照 cli-sample 的结构，自己实现 REPL、ReAct 循环、模型调用、工具注册与结果回填，得到一个本地可运行、能真正操作文件的 CLI Agent。

## 作业概览

- **作业目标**：仿照 cli-sample 重写一个 CLI 客户端，掌握 CLI 应用的基本组成——REPL 交互、ReAct 循环、模型调用、工具注册与工具结果回填。
- **核心任务**：参考 cli-sample 的结构，完成 react loop、工具注册、6 个本地工具（read/write/edit/bash/glob/grep）。
- **关键要求**：参考 cli-sample 的组织方式，但**自行完成代码重写**；不得用硬编码答案或伪造工具调用代替真实流程（自测用 FakeLLM 驱动你的循环，工具必须真实执行，伪造不了）。
- **最终效果**：运行客户端后，用户在终端自然语言交互，Agent 按需选择并执行工具，完成任务后给出最终回答：

```text
>>> 在 /tmp/lesson4-demo 下创建 notes.md，写入"今天学了 ReAct 循环"
  [turn 1] 🔧 write_file({'path': '/tmp/lesson4-demo/notes.md', ...})
        → successfully wrote file: ...
  已创建 /tmp/lesson4-demo/notes.md
>>> 把 notes.md 里的"循环"改成"loop"
  [turn 1] 🔧 edit_file({...})
        → successfully edited file: ...
>>> demo 目录里哪些文件提到 loop？
  [turn 1] 🔧 grep({'pattern': 'loop', 'path': '/tmp/lesson4-demo'})
        → found 1 matches: notes.md:1:...
  notes.md 第 1 行提到 loop。
```

## 黑盒 vs 白盒

| | cli-sample（参照物） | 本作业（你写的） |
|---|---|---|
| 循环 | `StatelessReactAgent.step()` 内部全自动 | `mycli/agent.py` 自己写 |
| 模型调用 | SDK LLM 模块 | `openai` 包，`mycli/llm.py` |
| 工具注册 | SDK `ToolManager` | `mycli/registry.py`（已给） |
| REPL | `cli_sample.py` | `main.py`（已给） |

```text
REPL (main.py, 已给)
  └─ agent_loop (TODO 7, 核心)
       ├─ llm_chat (TODO 1) ── openai 兼容端点
       ├─ TOOLS / call_tool (registry.py, 已给; 工具在 tools.py 注册)
       │     └─ read_file 已给 + 5 个工具 (TODO 2-6)
       └─ 回填: {"role": "tool", "tool_call_id": ..., "content": ...} ← 循环的闭环
```

> 本作业只需要 `openai` + `python-dotenv`（公网 PyPI 直装），**不需要 tongagents wheel**；SDK 黑盒版就在 `../cli-sample/` 供对照。

## 脚手架

```text
lesson4/homework/
├── README.md            # 本文件
├── pyproject.toml       # openai + python-dotenv (无需 tongagents)
├── .env.example         # OPENAI_* 三件套模板
├── main.py              # REPL 入口 (已给)
├── check_homework.py    # 9 项自测, 无 Key 无网络
└── mycli/
    ├── llm.py           # TODO(1): llm_chat 模型调用
    ├── tools.py         # TODO(2)-(6): 5 个工具 (read_file 已给样例)
    ├── registry.py      # 工具注册表 (已给)
    └── agent.py         # TODO(7): agent_loop —— 全作业核心
```

## 第 0 步：环境

```bash
cd lesson4/homework
python3 -m venv .venv && source .venv/bin/activate
pip install -e .        # 只装 openai + python-dotenv (公网 PyPI)
cp .env.example .env    # 填 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
```

（服务商选择见 `../../lesson4/README.md` 的三选一表格；模型须支持 function calling。）

## 第 1 步：读参照物

1. `../../lesson4/lesson4_tools_mcp_cli_skill.ipynb` 2.4 节（cell 17）——`agent_loop` 的逐行讲解，本作业就是把教学版落成正式版；
2. `../cli-sample/cli_sample.py`——SDK 黑盒版，看 REPL 与工具的组织方式；
3. `../cli-sample/tools/`——6 个工具的参考实现（可读，但要自己写）。

## 第 2 步：TODO(1) `llm.py`

实现 `llm_chat(messages, tools=None)`：调一次 `chat.completions`，返回 `resp.choices[0].message`。注意 tools 为空时不要传该参数。

## 第 3 步：TODO(2)-(6) `tools.py` 五个工具

`read_file` 已给完整样例（函数 + schema + register 三件套）。照它的模式实现 write/edit/bash/glob/grep——schema 已给出，只写函数体；行为对照 `../cli-sample/tools/` 同名工具；约定：**失败也不抛异常，返回 `"error: ..."` 字符串**（错误要能回传给模型）。

## 第 4 步：TODO(7) `agent.py` 循环（核心）

按注释四步实现 `agent_loop`：初始化 messages → 循环调 `llm(messages, tools=TOOLS)` → 无 `tool_calls` 返回最终回答 → 有则先 append assistant 消息、再逐个 `call_tool` 并回填 `role=tool` 消息；`max_turns` 兜底。

## 第 5 步：自测（无 Key 无网络）

```bash
cd lesson4/homework && python check_homework.py
```

9 项全过即达标。test_07-09 用 **FakeLLM**（脚本化假模型，形状对齐 openai 返回值）驱动你的循环：模型"说要写文件"，你的循环就必须真的写盘并按协议回填——这就是"不得伪造工具调用"的可验证形式。

## 第 6 步：接真模型运行

```bash
cd lesson4/homework && python main.py
```

按"最终效果"里的三连场景验收：创建 → 编辑 → 搜索，全程观察 `[turn N] 🔧` 逐轮日志。

## 验收标准

- `check_homework.py` 9 项全部通过（含 FakeLLM 的回填/并行/兜底三项）；
- `python main.py` 真机完成"创建→编辑→搜索"连续场景，工具真实生效（文件真的变了）；
- 提交：`mycli/` 的修改 + 一段真机对话记录（含 `[turn]` 日志）。

## 延伸思考（选做）

- 把 `max_turns` 调成 1 再跑三连场景，哪一步失败了？调成 100 有什么风险？
- 什么时候模型会一轮并行发多个 tool_call（test_08 的情形），什么时候拆成多轮？
- 写完后重读 `../cli-sample/cli_sample.py`：SDK 的 `step()` 替你做了 TODO(1)/(7) 里的哪几步？（Lesson 5 将回到 SDK 路线）
- 给 `bash` 加命令白名单（课件 3.x 的安全话题）：拒绝 `rm -rf` 类命令，怎么改既不误伤又不放行？
