# cli-sample

最简 [TongAgents](https://github.com/temp-bigai/Tong-Agent) CLI 样例 (接真实 LLM).

仿造 Tong-Agent 项目的 CLI, 但极简化: **单文件, REPL 循环, 3 个 OS 工具, OpenAI 兼容 LLM + function calling**.
教学目的: 演示如何用 `tongagents.agent.Agent` 写一个最小可运行 CLI,
不依赖复杂的 `tongagents-cli` (那是 TUI + session + skills 全套).

---

## 依赖

- Python >= 3.11
- [tongagents SDK 2.7.20](https://pypi.org/project/tongagents/2.7.20/) (从 [BigAI Nexus](https://nexus.mybigai.ac.cn/) 内网源装)
- `openai` (>=1.0) — 调 OpenAI 兼容 API
- `python-dotenv` — 读 `.env`

---

## 安装

```bash
# 1. clone
git clone git@github.com:temp-bigai/tongagents-course.git
cd tongagents-course/cli-sample

# 2a. 用 pip (从内网 nexus 装 tongagents)
pip install tongagents==2.7.20 openai python-dotenv
#    (或先配 pip.conf: index-url = https://nexus.mybigai.ac.cn/repository/pypi/simple/)

# 2b. 用 uv (推荐, 已配 pyproject.toml)
uv sync
```

> 🍎 **macOS 注意**: Nexus 上的 tongagents wheel 只有 Linux/Windows 版,
> mac 上 `uv sync` 会报 `no matching distribution`. 解决:
> `uv sync --no-group tongagents` 跳过, 或改用 `pip install`.

---

## 用真实 LLM 跑通 (推荐)

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
> override=True 让 `.env` 优先, Tong-Agent 内网 LLM 才能跑通.

REPL 示例 (Tong-Agent 内网 doubao-seed-2-0-pro):

```
============================================================
  cli-sample: TongAgents CLI 极简样例 (LLM 真实调用)
============================================================
  内置工具 (LLM 自动选择):
    list_dir(path=".")    列出目录
    read_file(path, ...)  读文件 (前 200 行)
    write_file(path, ...) 写文件
  模型: doubao-seed-2-0-pro-260215    端点: http://10.1.53.240
============================================================
>>> 列出当前目录有哪些文件
  当前目录下有以下文件:
  - .env.example
  - README.md
  - cli_sample.py
  - pyproject.toml

>>> 读 README.md
  cli-sample 是一个最简 TongAgents CLI 样例, 用 REPL...

>>> 写一个 hello.txt 内容是 hello world
  written: hello.txt (11 chars)

>>> 你好
  你好! 有什么可以帮你的吗?

>>> exit
bye!
```

---

## 不调 LLM 的极简模式

如果你不想装 SDK / 不调 LLM, 只想看 REPL 骨架, 也可以用 stdin 模拟:

```bash
printf '列出当前目录\n你好\nexit\n' | python cli_sample.py
# 但 step() 会真的去调 LLM, 没 API key 会报错.
```

---

## 工具列表

| 工具 | 作用 | OpenAI function schema |
|---|---|---|
| `list_dir(path=".")` | 列出目录内容 (按名字排序) | `path: string` |
| `read_file(path, max_lines=200)` | 读文件, 超 200 行截断并提示 | `path: string`, `max_lines: int` |
| `write_file(path, content)` | 写文件, 自动建父目录 | `path: string`, `content: string` |

3 个工具以纯 Python 函数定义在 `cli_sample.py`, 注册到 `TOOL_SCHEMAS`
(OpenAI function calling 格式) + `TOOL_IMPLS` (函数实现) 两个 map 里.

---

## 文件结构

```
cli-sample/
├── cli_sample.py       # 主程序 (REPL + Agent + LLM + 工具)
├── pyproject.toml      # 依赖 tongagents==2.7.20 + openai + python-dotenv
├── README.md           # 本文件
└── .env.example        # API key + BASE_URL + MODEL 配置模板
```

---

## 测试

### 1. 静态语法测试 (不调 SDK / LLM)

```bash
python -c "import ast; ast.parse(open('cli_sample.py').read()); print('cli_sample.py syntax OK')"
```

### 2. 工具单测 (不调 LLM)

```bash
python -c "
from cli_sample import list_dir, read_file, write_file
print('list_dir:', list_dir('.'))
write_file('/tmp/cli_sample_test.txt', 'hello world')
print('read_file:', read_file('/tmp/cli_sample_test.txt'))
"
```

### 3. Agent 单测 (需 .env)

```bash
# 先 cp Tong-Agent .env
python -c "
from cli_sample import CliSampleAgent
agent = CliSampleAgent()
for q in ['列出当前目录', '读 README.md', '你好']:
    print(f'>>> {q}')
    print(f'  {agent.step(q)[:200]}')
"
```

### 4. REPL 端到端测试 (需 .env)

```bash
cp ~/work/codework/tong_agents/Tong-Agent/.env .env
printf '列出当前目录\n你好\nexit\n' | python cli_sample.py
```

---

## 与 TongAgentCLI 的区别

| 维度 | TongAgentCLI (官方) | cli-sample (本样例) |
|---|---|---|
| 代码量 | ~几千行 (TUI + skills + session) | ~250 行 (单文件) |
| LLM 调用 | 自动 (tool calling + agent loop) | 调 `openai` SDK, 单轮最多 3 轮 tool call 循环 |
| 工具来源 | `@tool` 装饰器 + ToolRegistry | 普通 Python 函数 + `TOOL_SCHEMAS` / `TOOL_IMPLS` |
| 学习曲线 | 高 (TUI / session / skills 概念) | 低 (一个 `step()` 看懂) |

适合想看 **最小可运行骨架** 的同学. 想看生产级 CLI 看 `tongagents-cli`.

---

## 关联仓库

- [Tong-Agent](https://github.com/temp-bigai/Tong-Agent) - 完整 SDK + CLI
- [tongagents-course](https://github.com/temp-bigai/tongagents-course) - 课程仓库 (本仓库)
- [tongagents SDK 2.7.20](https://pypi.org/project/tongagents/2.7.20/) - SDK 版本
