# cli-sample

最简 [TongAgents](https://github.com/temp-bigai/Tong-Agent) CLI 样例 (走 SDK).

仿造 Tong-Agent 项目的 CLI, 但极简化: **单文件, REPL 循环, 用 SDK 的
`StatelessReactAgent` + 11 个默认工具**, **同步 `step()` 调用**, **不调 `.stream()`**.
教学目的: 演示怎么用 tongagents SDK 写一个最小可运行 CLI.

---

## 依赖

- Python >= 3.11
- [tongagents SDK 2.7.20](https://pypi.org/project/tongagents/2.7.20/) (从 [BigAI Nexus](https://nexus.mybigai.ac.cn/) 内网源装)
- [tongagents-cli 2.7.20](https://pypi.org/project/tongagents-cli/) (default_agent 工具定义 + `register_default_tools`)
- `python-dotenv` — 读 `.env`

---

## 安装

```bash
# 1. clone
git clone git@github.com:temp-bigai/tongagents-course.git
cd tongagents-course/cli-sample

# 2a. 用 pip (从内网 nexus 装)
pip install tongagents==2.7.20 tongagents-cli python-dotenv
#    (或先配 pip.conf: index-url = https://nexus.mybigai.ac.cn/repository/pypi/simple/)

# 2b. 用 uv (推荐, 已配 pyproject.toml)
uv sync
```

> 🍎 **macOS 注意**: Nexus 上的 tongagents wheel 只有 Linux/Windows 版,
> mac 上 `uv sync` 会报 `no matching distribution`. 解决:
> `uv sync --no-group tongagents` 跳过, 或改用 `pip install`.

---

## 用真实 LLM 跑通

```bash
# 1. 复制 Tong-Agent 的 .env (含 OPENAI_API_KEY + BASE_URL + MODEL)
cp ~/work/codework/tong_agents/Tong-Agent/.env .env

# (或) 自己填 OPENAI_* 三个变量
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=http://your-llm-endpoint/v1
export OPENAI_MODEL=your-model-name

# 2. 跑
python cli_sample.py
```

> ⚠️ **关键陷阱**: cli-sample 用 `load_dotenv(..., override=True)`,
> 因为 shell 里常设了 `OPENAI_API_KEY` / `OPENAI_BASE_URL` (例如指向
> 公开 minimax API), dotenv 默认不覆盖, 会导致 .env 不生效.

REPL 示例 (Tong-Agent 内网 doubao-seed-2-0-pro):

```
[boot] loading 11 default tools ...
[boot] building StatelessReactAgent ...
[boot] agent ready, llm=OpenAIModel, tools_loaded=[bash, read_file, write_file, edit_file, glob, grep, ...]

============================================================
  cli-sample: TongAgents CLI 极简样例 (走 SDK)
============================================================
  Agent: StatelessReactAgent (SDK default)
  工具: bash, edit_file, glob, grep, read_file, write_file, ...
  模型: doubao-seed-2-0-pro-260215
  端点: http://10.1.53.240
============================================================

>>> 列出当前目录有哪些文件
  当前目录下有以下文件:
  - .env.example
  - README.md
  - cli_sample.py
  - pyproject.toml

>>> 读 README.md 的前 5 行
  README.md 的前 5 行内容如下:
  # cli-sample
  最简 TongAgents CLI 样例 (走 SDK).
  ...

>>> 写一个 hello.txt 内容是 hello world
  已创建 hello.txt, 内容 "hello world".

>>> 你好
  你好! 有什么可以帮你的吗?

>>> exit
bye!
```

---

## SDK 用法核心

```python
from tongagents.agents.llm import ModelConfig, ModelProvider
from tongagents.agents.llm_agent import StatelessReactAgent, ReactAgentSetting
from tongagents.agents.llm_agent.defs import LLMInputEvent
from tongagents.agents.llm.messages import UserPromptMessage
from tongagents.tools.tool_manager import ToolManager
from tongagents_cli.default_agent.tools import register_default_tools

# 1. 注册 11 个默认工具
register_default_tools()

# 2. 构造 agent
llm_config = ModelConfig(model_provider=ModelProvider.OPENAI_COMPATIBLE)
#    ↑ 从 env 自动读 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
settings = ReactAgentSetting(
    name="cli-sample",
    llm_config=llm_config,
    tool_identifier_list=list(ToolManager.tool_classes.keys()),
    system_prompt="你是 cli-sample agent, ...",
)
agent = StatelessReactAgent(agent_settings=settings)

# 3. 同步 step — 不调 .stream()
wrap = LLMInputEvent(input=[UserPromptMessage("你的问题")])
actions = agent.step(wrap)  # ← 一次同步返回 list[Action]
for a in actions:
    if hasattr(a, "is_final_response") and a.is_final_response:
        print(a.content)
```

> ⚠️ **第二个坑**: `LLMInputEvent.input` 必须是 **`list[UserPromptMessage]`**,
> 不能传 `str` 或单个 `UserPromptMessage`. SDK 内部 `plan()` 会做
> `[*observation.input, model_response]` 展开, 单个对象不能 unpack, 会抛
> `TypeError: 'UserPromptMessage' object is not iterable`.

---

## 默认工具列表 (11 个)

| 工具 | 作用 |
|---|---|
| `bash` | 跑 shell 命令 |
| `read_file` | 读文件 |
| `write_file` | 写文件 |
| `edit_file` | 精确字符串替换 |
| `glob` | 文件名匹配 (e.g. `**/*.py`) |
| `grep` | 内容正则搜索 |
| `exa_search` | 网络搜索 (需 exa key) |
| `skill` | 加载 skill 文档 |
| `delegate_task` | 后台委派任务 |
| `query_background_process` | 查询后台任务 |
| `stop_task` | 停止后台任务 |

---

## 文件结构

```
cli-sample/
├── cli_sample.py       # 主程序 (REPL + SDK agent + step)
├── pyproject.toml      # 依赖 tongagents==2.7.20 + tongagents-cli + python-dotenv
├── README.md           # 本文件
└── .env.example        # API key + BASE_URL + MODEL 配置模板
```

---

## 测试

### 1. 静态语法测试

```bash
python -c "import ast; ast.parse(open('cli_sample.py').read()); print('cli_sample.py syntax OK')"
```

### 2. SDK 导入测试 (不调 LLM)

```bash
python -c "
import os
from dotenv import load_dotenv
load_dotenv('~/work/codework/tong_agents/Tong-Agent/.env', override=True)
from tongagents_cli.default_agent.tools import register_default_tools
register_default_tools()
from tongagents.tools.tool_manager import ToolManager
print('tools:', sorted(ToolManager.tool_classes.keys()))
"
```

### 3. REPL 端到端测试 (需 .env)

```bash
cp ~/work/codework/tong_agents/Tong-Agent/.env .env
printf '你好\n列出当前目录\nexit\n' | python cli_sample.py
```

---

## 与 TongAgentCLI 的区别

| 维度 | TongAgentCLI (官方) | cli-sample (本样例) |
|---|---|---|
| 代码量 | ~几千行 (TUI + skills + session) | ~200 行 (单文件) |
| Agent | `WorkflowWithMemory.create(json).stream()` | `StatelessReactAgent.step()` (同步) |
| 流式 | 必须 `.stream()` | ❌ 不调, 一次同步返回 |
| 工具 | 11 个 SDK 默认 + skills + plugins | 11 个 SDK 默认 |
| 学习曲线 | 高 (workflow JSON / session / plugins) | 低 (一个 `step()` 看懂) |

适合想看 **最小可运行骨架** 的同学. 想看生产级 CLI 看 `tongagents-cli`.

---

## 关联仓库

- [Tong-Agent](https://github.com/temp-bigai/Tong-Agent) - 完整 SDK + CLI
- [tongagents-course](https://github.com/temp-bigai/tongagents-course) - 课程仓库 (本仓库)
- [tongagents SDK 2.7.20](https://pypi.org/project/tongagents/2.7.20/) - SDK 版本
- [tongagents-cli 2.7.20](https://pypi.org/project/tongagents-cli/) - CLI 工具
