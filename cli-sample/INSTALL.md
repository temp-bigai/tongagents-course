# cli-sample 安装 — 本地 wheel 方式 (无 Nexus 权限)

> **v0.4.0 重要变更**: 本示例 **不再依赖 BigAI Nexus 私有源**。开发者只需要拿到项目维护者提供的 2 个本地 wheel 文件, 用 `pip install ./wheels/*.whl` 即可, 完全离线安装。

---

## 0. 前置

| 项目 | 要求 |
|---|---|
| Python | **>= 3.11**（推荐 3.12） |
| pip | **>= 21.3**（PEP 517 支持） |
| 操作系统 | Linux x86_64 / Windows amd64 / macOS |
| 网络 | **不需要**访问 Nexus, 全部依赖在本地 wheel |

> ✅ **不需要** pip.conf / Nexus 凭据 / [tool.uv.sources]

---

## 1. 准备 wheels 目录

从项目维护者获取 wheels 文件, 放到 `wheels/` 目录下:

```bash
cd tongagents-course
mkdir -p wheels
# 把维护者给的 wheel 复制到 wheels/
cp /path/to/tongagents-*.whl wheels/
cp /path/to/tongagents_cli-*.whl wheels/

ls -lh wheels/
# 期望看到:
# tongagents-2.7.21-cp312-cp312-linux_x86_64.whl   (16M, 推荐)
# tongagents-2.7.21-py3-none-any.whl                (38M, 跨平台)
# tongagents_cli-1.8.22-cp312-cp312-linux_x86_64.whl (5.1M, 推荐)
# tongagents_cli-1.8.22-py3-none-any.whl            (7.8M, 跨平台)
```

> 💡 **优先用 `cp312-cp312-linux_x86_64.whl`**（小）；macOS / ARM64 / 其他 Python 版本请用 `py3-none-any.whl`（含 C 源码）。

---

## 2. 创建虚拟环境

```bash
cd cli-sample
python3 -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows PowerShell

python -m pip install --upgrade pip  # 升级 pip (避免老版本解析问题)
```

---

## 3. 安装本地 wheel (核心步骤)

```bash
# 3.1 装 tongagents SDK (TongAgent/Agent/StatelessReactAgent)
pip install ../wheels/tongagents-*.whl

# 3.2 装 tongagents_cli (可选, cli-sample 不直接用, 但 SDK 可能依赖)
pip install ../wheels/tongagents_cli-*.whl

# 3.3 装 cli-sample 自身 (含本地 tools/ 子包 + python-dotenv)
pip install -e .
```

> ⚠️ **顺序很重要**: 先 wheel, 再 `-e .`。否则 cli-sample 会去 PyPI 找 tongagents 失败。

---

## 4. 验证安装

```bash
# 4.1 验证 Python 模块
python -c "import tongagents; print('tongagents', tongagents.__version__)"

# 4.2 验证 SDK 核心 API
python -c "
from tongagents.agent import Agent, AgentSettings
print('SDK OK')
print('AgentSettings fields:', list(AgentSettings.model_fields.keys()))
"

# 4.3 验证本地 tools 子包
python -c "
import sys; sys.path.insert(0, '.')
from tools import bash_tool, read_file_tool, write_file_tool
print('local tools OK')
"
```

预期输出:

```
tongagents 2.7.21
SDK OK
AgentSettings fields: [...]
local tools OK
```

---

## 5. 配置 LLM 环境变量

```bash
# 5.1 复制 .env 模板
cp .env.example .env

# 5.2 编辑 .env, 填入实际 LLM 配置 (OpenAI 兼容端点)
# OPENAI_API_KEY=sk-your-key
# OPENAI_BASE_URL=http://your-llm/v1
# OPENAI_MODEL=your-model
vim .env
```

---

## 6. 跑示例

```bash
python cli_sample.py
# 启动 REPL, 输入问题, SDK 自动调本地 tools
# 输入 'exit' / 'quit' / Ctrl+D 退出
```

---

## 7. 常见问题

### 7.1 wheel 与本地 Python ABI 不匹配

错误: `tongagents-2.7.21-cp312-cp312-linux_x86_64.whl is not a supported wheel on this platform.`

解决:

```bash
# 检查 Python 版本
python --version   # 期望 3.12.x

# 如果是 3.11 / 3.13 / ARM64 / macOS, 用通用 wheel
pip uninstall tongagents tongagents-cli -y
pip install ../wheels/tongagents-2.7.21-py3-none-any.whl
pip install ../wheels/tongagents_cli-1.8.22-py3-none-any.whl
```

### 7.2 `ModuleNotFoundError: No module named 'tongagents'`

- 确认 wheel 已装: `pip show tongagents`
- 确认 wheel 在 `../wheels/` 目录下 (相对 cli-sample)
- 用绝对路径试一下: `pip install /abs/path/to/wheels/tongagents-*.whl`

### 7.3 CLI 跑起来但 LLM 不响应

- 检查 `.env` 是否配了 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`
- 跑: `python -c "from dotenv import dotenv_values; print(dotenv_values('.env'))"`

---

## 8. 升级 / 卸载

```bash
# 升级 wheel
pip install --upgrade ../wheels/tongagents-*.whl
pip install --upgrade ../wheels/tongagents_cli-*.whl

# 卸载全部
pip uninstall tongagents tongagents-cli tongagents-cli-sample -y
```

---

## 9. 为什么用本地 wheel?

| 方案 | 优点 | 缺点 |
|---|---|---|
| **本地 wheel (推荐)** | 离线 / 不需要 Nexus 凭据 / 跨环境一致 / 版本可控 | 需维护者分发 wheel |
| Nexus pip.conf | 自动解析依赖 | 需要内网 + 凭据 + 写 ~/.config/pip/pip.conf |
| `[tool.uv.sources]` editable | 调试方便 | 需要 uv + 内网 + 编辑源 |

本示例面向**外部开发者**（无 Nexus 权限），统一用本地 wheel。
