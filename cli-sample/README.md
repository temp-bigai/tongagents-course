# cli-sample

最简 [TongAgents](https://github.com/temp-bigai/Tong-Agent) CLI 样例.

仿造 Tong-Agent 项目的 CLI, 但极简化: **单文件, REPL 循环, 3 个 OS 工具**.
教学目的: 演示如何用 `tongagents.agent.Agent` 写一个最小可运行 CLI,
不依赖复杂的 `tongagents-cli` (那是 TUI + session + skills 全套).

---

## 依赖

- Python >= 3.11
- [tongagents SDK 2.7.20](https://pypi.org/project/tongagents/2.7.20/) (从 [BigAI Nexus](https://nexus.mybigai.ac.cn/) 内网源装)
- `python-dotenv` (读 `.env`)

---

## 安装

```bash
# 1. clone
git clone git@github.com:temp-bigai/tongagents-course.git
cd tongagents-course/cli-sample

# 2a. 用 pip (从内网 nexus 装 tongagents)
pip install tongagents==2.7.20 python-dotenv
#    (或先配 pip.conf: index-url = https://nexus.mybigai.ac.cn/repository/pypi/simple/)

# 2b. 用 uv (推荐, 已配 pyproject.toml)
uv sync

# 3. 配 API key
cp .env.example .env
# 编辑 .env, 按 README 三选一填 OPENAI_API_KEY (本样例 echo 不调 LLM, 可选)
```

> 🍎 **macOS 注意**: Nexus 上的 tongagents wheel 只有 Linux/Windows 版,
> mac 上 `uv sync` 会报 `no matching distribution`. 解决:
> `uv sync --no-group tongagents` 跳过 (本样例 echo 不需要 tongagents 实际调 LLM).

---

## 运行

```bash
$ python cli_sample.py

============================================================
  cli-sample: TongAgents CLI 极简样例
============================================================
  输入问题, 按回车. 输入 'exit' / 'quit' / 'q' / Ctrl+D 退出.
  内置工具 (路由关键词):
    list [path]   列出目录 (默认当前目录)
    read <path>   读文件 (前 200 行)
    write <path> with content "..."   写文件
  默认: echo 回显
============================================================
>>> list
  README.md
  pyproject.toml
  cli_sample.py
  .env.example

>>> read README.md
  # cli-sample
  ...

>>> write /tmp/hello.txt with content "hi from cli-sample"
  written: /tmp/hello.txt (22 chars)

>>> hello
  [echo] hello

>>> exit
bye!
```

也可以管道:

```bash
printf "list\nexit\n" | python cli_sample.py
```

---

## 工具列表

| 工具 | 作用 |
|---|---|
| `list_dir(path=".")` | 列出目录内容 (按名字排序) |
| `read_file(path, max_lines=200)` | 读文件, 超 200 行截断并提示 |
| `write_file(path, content)` | 写文件, 自动建父目录 |

3 个工具以纯 Python 函数定义在 `cli_sample.py`, 也可作为 `TOOLS` dict 暴露给 LLM 做 OpenAI function calling.

---

## 文件结构

```
cli-sample/
├── cli_sample.py       # 主程序 (REPL + Agent + 工具)
├── pyproject.toml      # 依赖 tongagents==2.7.20 + python-dotenv
├── README.md           # 本文件
└── .env.example        # API key 配置模板
```

---

## 测试

### 1. 静态语法测试 (不调 SDK)

```bash
python -c "import ast; ast.parse(open('cli_sample.py').read()); print('cli_sample.py syntax OK')"
```

### 2. 工具单测 (不调 Agent)

```bash
python -c "
from cli_sample import list_dir, read_file, write_file
print('list_dir:', list_dir('.'))
write_file('/tmp/cli_sample_test.txt', 'hello world')
print('read_file:', read_file('/tmp/cli_sample_test.txt'))
"
```

### 3. Agent 单测

```bash
python -c "
from cli_sample import CliSampleAgent
agent = CliSampleAgent()
for r in agent.run(iter(['list', 'read README.md', 'hello'])):
    print(repr(r))
"
```

### 4. REPL 端到端测试 (echo 输入)

```bash
printf 'list\nexit\n' | python cli_sample.py
```

---

## 与 TongAgentCLI 的区别

| 维度 | TongAgentCLI (官方) | cli-sample (本样例) |
|---|---|---|
| 代码量 | ~几千行 (TUI + skills + session) | ~150 行 (单文件) |
| LLM 调用 | 自动 (tool calling + agent loop) | 否, 关键词路由 echo |
| 工具来源 | `@tool` 装饰器 + ToolRegistry | 普通 Python 函数 + dict |
| 学习曲线 | 高 (TUI / session / skills 概念) | 低 (一个 `step()` 看懂) |

适合想看 **最小可运行骨架** 的同学. 想看生产级 CLI 看 `tongagents-cli`.

---

## 关联仓库

- [Tong-Agent](https://github.com/temp-bigai/Tong-Agent) - 完整 SDK + CLI
- [tongagents-course](https://github.com/temp-bigai/tongagents-course) - 课程仓库 (本仓库)
- [tongagents SDK 2.7.20](https://pypi.org/project/tongagents/2.7.20/) - SDK 版本
