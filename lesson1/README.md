# Lesson 1 — 第一个 Echo Agent

> TongAgents SDK 入门：安装 → 配置 → 第一个 Agent → Workflow 编排

---

## 🎯 学习目标

完成本课后，你将掌握：

1. ✅ 从**本地 wheel** 安装 TongAgents SDK + CLI（**不依赖 BigAI Nexus**）
2. ✅ 理解 `tongagents` 包的核心 API：`Agent`、`AgentSettings`、`node_declare`、`Workflow`
3. ✅ 用 3 种方式调用 Agent（直接调用 / 流式 / Workflow 编排）
4. ✅ 编写你的第一个可运行、可测试的 TongAgents Agent

---

## 📂 目录结构

```
lesson1/
├── README.md              # 本文件（课程主入口）
├── INSTALL.md             # 详细安装文档（本地 wheel 方式）
├── pyproject.toml         # Python 项目配置（不含 nexus）
├── requirements.txt       # Python 依赖清单
├── .env.example           # 环境变量模板
├── echo_agent.py          # 主示例：Echo Agent（import tongagents）
├── agent_settings_demo.py # AgentSettings 用法详解
├── node_declare_demo.py   # @node_declare 装饰器用法详解
└── tests/
    ├── __init__.py
    ├── test_echo_agent.py     # Echo Agent 单元测试
    ├── test_agent_settings.py # AgentSettings 单元测试
    └── test_node_declare.py   # @node_declare 单元测试
```

> 💡 **`wheels/` 目录**: 本课程 3 个示例（`cli-sample/`、`lesson1/`、`lesson2/`）共用同一份
> wheel 文件, 放在**仓库根目录**的 `wheels/` 下。开发者 clone 后从项目维护者获取。

---

## 🚀 快速开始

### 1. 准备 wheels（一次性）

```bash
# 从项目维护者获取 wheel 文件, 放到仓库根目录 wheels/
cd tongagents-course
ls wheels/
# 期望看到:
# tongagents-2.7.21-cp312-cp312-linux_x86_64.whl
# tongagents_cli-1.8.22-cp312-cp312-linux_x86_64.whl
# (或 py3-none-any 通用 wheel)
```

### 2. 安装（5 分钟）

参考 [INSTALL.md](./INSTALL.md) 详细步骤。TL;DR：

```bash
cd lesson1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# 装本地 wheel (不走 nexus, 不走 [tool.uv.sources])
pip install ../wheels/tongagents-*.whl
pip install ../wheels/tongagents_cli-*.whl

# 装 lesson1 依赖
pip install -e .
```

### 3. 验证安装

```bash
# 验证 SDK + CLI
python -c "import tongagents; print('tongagents', tongagents.__version__)"
python -c "from tongagents.agent import Agent, AgentSettings; print('SDK OK')"
```

预期：`tongagents 2.7.21` + `SDK OK`

### 4. 跑 3 个示例

```bash
# 4.1 主示例: Echo Agent
python echo_agent.py

# 4.2 AgentSettings 用法
python agent_settings_demo.py

# 4.3 @node_declare 装饰器 + Workflow
python node_declare_demo.py
```

### 5. 跑测试

```bash
python -m pytest tests/ -v
```

---

## 🔑 核心概念

### 1. TongAgents SDK 的三大基石

| API | 所在模块 | 作用 |
|---|---|---|
| `Agent` | `tongagents.agent.Agent` | Agent 抽象基类，必须实现 `step` / `run` / `astep` / `arun` |
| `AgentSettings` | `tongagents.agent.AgentSettings` | Pydantic 模型，描述 Agent 的元信息与运行参数 |
| `node_declare` | `tongagents.workflow.simple_workflow.node_declare` | 装饰器，把函数/方法声明为工作流节点 |

### 2. Agent 生命周期

```
AgentSettings（配置） ──┐
                        ├──▶ Agent 实例 ──▶ step() / run() / astep() / arun()
AgentRunContext（运行时）┘
```

### 3. Workflow 节点

```
普通函数 ──▶ @node_declare() ──▶ Workflow.add_node(name, func) ──▶ Workflow.run(events)
                                    ▲
类方法   ──▶ @node_declare() ─────┤
                                    ▲
NodeBase 子类 ──▶ @node_declare() ──┘
```

---

## 💻 示例代码片段

### 最简 Echo Agent

```python
from tongagents.agent import Agent, AgentSettings


class EchoAgent(Agent):
    def step(self, event):
        return f"Echo: {event}"

    def run(self, events):
        for e in events:
            yield self.step(e)

    async def astep(self, event):
        return self.step(event)

    async def arun(self, events):
        async for e in events:
            yield await self.astep(e)


agent = EchoAgent(agent_setting=AgentSettings(name="echo"))
print(agent.step("Hello!"))  # → "Echo: Hello!"
```

完整代码见 [`echo_agent.py`](./echo_agent.py)。

### 最简 Workflow 节点

```python
from tongagents.workflow.simple_workflow import node_declare, Workflow


@node_declare(name="upper", edges=[("input", "output")])
def to_upper(events, context=None):
    for text in events:
        yield text.upper()


wf = Workflow()
wf.add_node("upper", to_upper)
print(list(wf.run(iter(["hello", "world"]))))
# → ["HELLO", "WORLD"]
```

完整代码见 [`node_declare_demo.py`](./node_declare_demo.py)。

---

## 🧪 测试

```bash
# 跑全部测试
python -m pytest tests/ -v

# 跑单个测试
python -m pytest tests/test_echo_agent.py -v
python -m pytest tests/test_agent_settings.py -v
python -m pytest tests/test_node_declare.py -v
```

测试覆盖：

| 测试文件 | 覆盖范围 |
|---|---|
| `test_echo_agent.py` | EchoAgent.step / run / astep / arun / AgentSettings 集成 |
| `test_agent_settings.py` | 默认值、显式覆盖、extra="allow"、序列化 |
| `test_node_declare.py` | 函数装饰器、类方法、NodeBase 子类、edges 声明 |

---

## 🛠 常见问题

### Q: 为什么用本地 wheel 而不是 Nexus？

A: **开发者通常无 BigAI 内网访问权限**。改用本地 wheel 后, 整个安装流程**完全离线**,
不依赖 Nexus 凭据 / `~/.config/pip/pip.conf` / `[tool.uv.sources]` editable 源。
课程维护者负责构建 + 分发 wheel, 开发者只负责 `pip install ./wheels/*.whl`。

### Q: wheel 与 Python 版本不匹配怎么办？

A: 默认提供 2 套 wheel:

- `cp312-cp312-linux_x86_64.whl` (推荐, 小) — Linux x86_64 + Python 3.12
- `py3-none-any.whl` (跨平台, 大) — 任何平台 + Python >= 3.11

macOS / ARM64 / 其他 Python 版本请用 `py3-none-any.whl`。

### Q: 我能在 Windows 上跑吗？

A: 可以。Linux wheel 是 `linux_x86_64`, Windows 需用 `py3-none-any.whl` (含 C 源码)。

### Q: 怎么升级？

```bash
pip install --upgrade ../wheels/tongagents-*.whl
pip install --upgrade ../wheels/tongagents_cli-*.whl
```

---

## 📚 下一步

- **lesson2**：Prompt Engineering 进阶（CoT / Self-Consistency / ToT / RAG）
- **lesson3**：LLM Agent（ReactAgent / ModelConfig）

---

## 📖 参考资料

- [INSTALL.md](./INSTALL.md) — 详细安装文档（本地 wheel 方式）
- [tongagents-course 仓库](https://github.com/temp-bigai/tongagents-course)
