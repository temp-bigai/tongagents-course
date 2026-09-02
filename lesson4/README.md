# Lesson 4 — Agent 的四件套：Tool、CLI、MCP 与 Skill

> 一个 Notebook 从零讲到能用：**Tool（函数调用）→ CLI（命令行工具）→ MCP（开放协议）→ Skill（操作手册）**，主线是把它们串起来的 **Agent Loop**。
> 示例由浅入深，前半部分**无需 API Key** 即可运行。
> 每个主题**双线呈现**：先手写白盒看清协议本身，再用 **TongAgents SDK** 复刻同一件事（黑盒对照），框架替你做了什么一目了然。

---

## 🎯 学习目标

完成本课后，你将掌握：

1. ✅ 手写工具的 JSON Schema，理解「实现 + 说明书」的分工
2. ✅ 从零实现完整的 Agent Loop（tool_call → 执行 → 回传 → 最终回答）
3. ✅ 把命令行包装成带白名单的安全工具交给模型
4. ✅ 用 FastMCP 写 MCP Server、作为 Client 连接、并桥接给 OpenAI 模型
5. ✅ 写符合规范的 Agent Skill，理解渐进式披露（progressive disclosure）
6. ✅ 面对新需求，判断该用 Tool / CLI / MCP / Skill 中的哪一个
7. ✅ 用 TongAgents SDK 对照实现每样能力：`@tool` / `ReactAgent` / `MCPClient` / `SkillTool`

---

## 📂 目录结构

```text
lesson4/
├── lesson4_tools_mcp_cli_skill.ipynb   # 主课件（唯一需要打开的文件）
├── pyproject.toml                      # uv 项目定义（依赖 + Python 版本）
├── uv.lock                             # 依赖锁定文件（保证环境可复现）
├── .python-version                     # Python 3.12
├── .env.example                        # 环境变量模板（复制为 .env）
└── .gitignore
```

> `mcp_weather_server.py` 和 `skills/` 目录是 Notebook 运行时自动生成的（`%%writefile`），不必提前创建。

---

## 🚀 快速开始

### 1. 前置：安装 uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或 brew install uv
```

### 2. 一键搭建环境

```bash
cd lesson4
uv sync          # 按 uv.lock 创建 .venv 并安装全部依赖（版本完全可复现）
```

### 2.5 TongAgents SDK（默认安装，无需额外命令）

notebook 的 **2.5 / 3.4 / 5.5 / 6.3 / 6.4 节**用 TongAgents SDK 做双段对照。`pyproject.toml` 已把 `tongagents` 组设为 uv **默认组**（`default-groups`），所以第 2 步的 `uv sync` 会自动从 BigAI Nexus 装上它（依赖较重，首次同步耐心等待）。Nexus 源也已配好（`[[tool.uv.index]]`，等价于 Lesson 1 INSTALL.md 的 pip.conf）。

> 🍎 **macOS 例外**：Nexus 上的 tongagents wheel 只有 **Linux / Windows** 版，mac 直接 `uv sync` 会报 `no matching distribution`。在 mac 上用 `uv sync --no-group tongagents` 跳过，上述小节自动降级显示「⏭️ 未安装」并跳过，其余章节不受影响。

### 3. 配置 `.env`（OpenAI 环境变量都放这里）

```bash
cp .env.example .env
```

编辑 `.env`，按你使用的服务三选一：

| 方案 | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `OPENAI_MODEL` |
|---|---|---|---|
| **OpenAI 官方**（默认） | [官方 Key](https://developers.openai.com/api/docs/) | `https://api.openai.com/v1` | `gpt-5.6-luna` |
| **智谱 GLM**（OpenAI 兼容） | [智谱 Key](https://open.bigmodel.cn/usercenter/apikeys) | Coding Plan 套餐：`https://open.bigmodel.cn/api/coding/paas/v4`；按量付费：`https://open.bigmodel.cn/api/paas/v4` | `glm-5.3`（两个端点不通用：Coding Plan 的 Key 配按量端点会报 `1113 余额不足`） |
| **其他兼容服务**（DeepSeek / vLLM 自部署…） | 对应 Key | 服务商提供的地址 | 支持工具调用的模型 |

`.env` 已被 `.gitignore` 忽略，不会提交到仓库。没有 Key 也能学：notebook 中需要真实模型的单元格会自动跳过并提示（第 1、2、4.1、5.1–5.2、6.1 节完全本地运行）。

### 4. 启动 Notebook

```bash
uv run jupyter lab lesson4_tools_mcp_cli_skill.ipynb
# 或经典界面：
uv run jupyter notebook lesson4_tools_mcp_cli_skill.ipynb
```

> ⚠️ 一定要用 `uv run` 启动：①内核用的才是本目录 `.venv`（含 openai / mcp / tongagents 等依赖）；② PATH 里才有 venv 的 `python`——5.5 节 TongAgents 的 `MCPClient` 拉起 MCP 子进程用的就是它。
> （macOS 上启动前先 `uv sync --no-group tongagents`，此后 `uv run` 会一直沿用这个降级环境。）

---

## 🔧 脚手架是怎么搭的（供复现）

本目录已包含 `uv.lock`，直接 `uv sync` 即可。如果想从零重建同样的环境，等价命令是：

```bash
uv init --python 3.12 --name tongagents-lesson4   # 生成 pyproject.toml / .python-version
uv add openai mcp python-dotenv pyyaml            # 运行时依赖
uv add jupyterlab notebook ipykernel              # Notebook 环境
# TongAgents 对照组：pyproject 里加 [dependency-groups] tongagents、
# [tool.uv] default-groups = ["tongagents"]、[[tool.uv.index]]（Nexus），
# 之后裸 uv sync 即包含它
```

各文件的作用：

| 文件 | 作用 |
|---|---|
| `pyproject.toml` | 声明依赖与版本约束，`uv add/remove` 会改这个文件 |
| `uv.lock` | 锁定每个包的精确版本，保证所有人 `uv sync` 出完全一致的环境 |
| `.python-version` | 声明 Python 版本，`uv` 会自动下载对应的解释器 |
| `.venv/` | 虚拟环境本体（不提交 git），删掉后 `uv sync` 可随时重建 |

常用 uv 命令速查：`uv sync`（按锁文件装环境）、`uv add <pkg>`（加依赖）、`uv remove <pkg>`、`uv run <cmd>`（在 .venv 中执行）、`uv lock --upgrade`（升级依赖版本）。

---

## 🧪 验证安装（无 Key 冒烟测试）

```bash
uv run python -c "import openai, mcp, yaml, dotenv, tongagents; print('deps OK')"
uv run jupyter nbconvert --to notebook --execute lesson4_tools_mcp_cli_skill.ipynb --output /tmp/l4-check.ipynb
```

第二条会从头执行整个 notebook（未配 Key 时模型相关单元格自动跳过），成功即环境就绪。

---

## ❓ 常见问题

- **Q：提示 `ModuleNotFoundError: No module named 'openai'`？**
  A：notebook 内核没用对环境。退出 Jupyter，确认用 `uv run jupyter lab` 启动；内核选 `Python 3 (ipykernel)`。

- **Q：MCP 单元格报 `FileNotFoundError: 'python'`？**
  A：MCP server 子进程要用当前 venv 的 Python 拉起。手写版（5.2）用 `sys.executable` 已处理；TongAgents 的 `MCPClient`（5.5）内部固定用命令 `python`，所以 Jupyter 必须用 `uv run jupyter lab` 启动（PATH 里有 venv 的 python）。

- **Q：没装 tongagents 会报错吗？**
  A：不会。2.5 / 3.4 / 5.5 / 6.3 / 6.4 节检测不到包时自动跳过并提示，其余章节不受影响。macOS 上请用 `uv sync --no-group tongagents`（默认组里没有它的 wheel）。

- **Q：tongagents 单元格报 `'_asyncio.Task' object has no attribute 'name'`？**
  A：Jupyter 内核自身运行在事件循环里，`MCPClient` 的同步封装会失效。课件 5.5 已把整段放进独立线程执行（`ThreadPoolExecutor`），仿写时保持这个结构。

- **Q：TongAgents 官方文档的示例跑不通？**
  A：仓库文档（`docs/sdk/`）滞后于 2.7.x 代码。已实测的差异：`MCPToolManager.initialize_from_mcp` 返回**工具类**而非实例（需 `[T() for T in ...]`）；skill 文件实际是 `SKILL.md`（大小写不敏感），不是旧文档的 `skill.md`。以源码为准。

- **Q：MCP 报 `Attempted to exit cancel scope in a different task...`？**
  A：`async with` 的 MCP 连接被跨单元格拆开（Jupyter 每个单元格是独立的异步任务）。notebook 已按「单单元格完成 连接→使用→关闭」设计，仿写时保持同一结构。

- **Q：项目目录被移动过，`.venv` 失效（jupyter/命令报旧的绝对路径）？**
  A：`.venv` 里的脚本记录了创建时的绝对路径，移动后失效。执行 `rm -rf .venv && uv sync` 重建即可，秒级完成。

- **Q：想换模型或换服务商？**
  A：只改 `.env` 三个变量（见上方表格），代码零改动。兼容服务对工具调用的支持程度可能不同。

---

## 📚 参考资料

- **OpenAI**：[Function Calling 指南](https://developers.openai.com/api/docs/guides/function-calling) · [Responses vs Chat Completions](https://developers.openai.com/api/docs/guides/responses-vs-chat-completions) · [Agents SDK（MCP 支持）](https://openai.github.io/openai-agents-python/mcp/)
- **Anthropic**：[Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) · [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) · [Agent Skills 工程博客](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- **示例仓库**：[claude-cookbooks](https://github.com/anthropics/claude-cookbooks)（tool_use / skills 系列 notebook）
- **协议与标准**：[Model Context Protocol](https://modelcontextprotocol.io) · [Agent Skills 开放标准](https://agentskills.io)
- **TongAgents SDK（内部）**：源码仓库 `Tong-Agent/`（`tongagents/tools/`、`tongagents/agents/llm_agent/`）· 文档 `Tong-Agent/docs/sdk/documentation/`（滞后于 2.7.x 代码，以源码为准）· 安装：BigAI Nexus（配置见 Lesson 1 的 INSTALL.md）
- **工具链**：[uv 文档](https://docs.astral.sh/uv/)
