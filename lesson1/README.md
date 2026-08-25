# Lesson 1 — 第一个 Echo Agent

> TongAgents SDK 入门：安装 → 配置 → 第一个 Agent → Workflow 编排

---

## 🎯 学习目标

完成本课后，你将掌握：

1. ✅ 从 **BigAI Nexus**（私有 PyPI）安装 TongAgents SDK + CLI
2. ✅ 理解 `tongagents` 包的核心 API：`Agent`、`AgentSettings`、`node_declare`、`Workflow`
3. ✅ 用 3 种方式调用 Agent（直接调用 / 流式 / Workflow 编排）
4. ✅ 编写你的第一个可运行、可测试的 TongAgents Agent

---

## 📂 目录结构

```
lesson1/
├── README.md              # 本文件（课程主入口）
├── INSTALL.md             # 详细安装文档（pip.conf + Nexus wheel）
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

---

## 🚀 快速开始

### 1. 安装（5 分钟）

参考 [INSTALL.md](./INSTALL.md) 详细步骤。TL;DR：

```bash
# 1.1 配置 pip 使用 BigAI Nexus
mkdir -p ~/.config/pip
cat > ~/.config/pip/pip.conf << 'EOF'
[global]
index-url = https://nexus.mybigai.ac.cn/repository/pypi/simple/
extra-index-url = https://pypi.org/simple
trusted-host =
    nexus.mybigai.ac.cn
    pypi.org
EOF

# 1.2 创建 venv 并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 验证安装

```bash
# 验证 SDK + CLI
tongagents --version
python -c "import tongagents; print(tongagents.__version__)"
```

预期：`tongagents-cli, version 1.8.19` + `2.7.19`

### 3. 跑第一个 Echo Agent

```bash
# 3.1 主示例
python echo_agent.py

# 3.2 辅助示例
python agent_settings_demo.py
python node_declare_demo.py
```

### 4. 跑测试

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

### Q: 为什么用 Nexus 而不是 PyPI？

A: `tongagents` 依赖 `tong-env`（BigAI 平台私有包），只在 Nexus 镜像中存在。同时 Nexus 同步了所有公开 PyPI 包作为 fallback（`extra-index-url`）。

### Q: 我能在 Windows 上跑吗？

A: 可以。Nexus 上有 `cp312-cp312-win_amd64.whl`。直接 `pip install tongagents tongagents-cli` 即可。

### Q: 我能在 Apple Silicon (M1/M2) 上跑吗？

A: 当前发布的 wheel 只有 `linux_x86_64` 和 `win_amd64`。Apple Silicon 需要源码安装：

```bash
pip install tongagents --no-binary :all: \
    --index-url https://nexus.mybigai.ac.cn/repository/pypi/simple/
```

### Q: 怎么升级？

```bash
pip install --upgrade tongagents tongagents-cli
```

---

## 📚 下一步

- **lesson2**：Workflow 进阶（条件分支 / 循环 / 异常处理）
- **lesson3**：LLM Agent（ReactAgent / ModelConfig）
- **选修1**：把 Echo Agent 接入 MCP Server

---

## 📖 参考资料

- [INSTALL.md](./INSTALL.md) — 详细安装文档
- [tongagents-course 仓库](https://github.com/temp-bigai/tongagents-course)
- [BigAI Nexus](https://nexus.mybigai.ac.cn/)
