# Lesson 2 安装文档 — CoT + RAG + PromptTemplate

本文档详细描述如何从 **BigAI Nexus**（私有 PyPI 镜像）安装 TongAgents SDK 与本课所需的测试依赖。Lesson 2 复用 Lesson 1 的全部安装流程，因此本课沿用同一份 Nexus 配置与 SDK 版本。

---

## 0. 环境先决条件

| 项目 | 要求 |
|---|---|
| Python | **>= 3.11**（推荐 3.12） |
| pip | **>= 21.3**（支持 PEP 517） |
| 操作系统 | Linux x86_64 / Windows amd64 / macOS（仅源码） |
| 网络 | 可访问 `nexus.mybigai.ac.cn` |

```bash
python3 --version  # 确认 3.11 / 3.12
python3 -m pip --version
```

---

## 1. 配置 pip 使用 BigAI Nexus

### 1.1 找到 pip 配置文件位置

```bash
python3 -m pip config debug  # 查看当前生效的配置
```

### 1.2 写入 pip.conf（推荐）

#### Linux / macOS：`~/.config/pip/pip.conf`

```bash
mkdir -p ~/.config/pip
cat > ~/.config/pip/pip.conf << 'EOF'
[global]
index-url = https://nexus.mybigai.ac.cn/repository/pypi/simple/
extra-index-url = https://pypi.org/simple
trusted-host =
    nexus.mybigai.ac.cn
    pypi.org
EOF
```

#### Windows：`%APPDATA%\pip\pip.ini`

```ini
[global]
index-url = https://nexus.mybigai.ac.cn/repository/pypi/simple/
extra-index-url = https://pypi.org/simple
trusted-host =
    nexus.mybigai.ac.cn
    pypi.org
```

### 1.3 临时使用 Nexus（无需改配置）

```bash
pip install tongagents \
    --index-url https://nexus.mybigai.ac.cn/repository/pypi/simple/ \
    --extra-index-url https://pypi.org/simple
```

---

## 2. 创建虚拟环境（推荐）

```bash
python3 -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows PowerShell
```

---

## 3. 安装 TongAgents SDK

### 3.1 安装最新版（Cython 加密 wheel）

```bash
pip install --upgrade tongagents
```

**当前最新版本**：`tongagents-2.7.19`（Cython 加密 wheel，~16 MB）

### 3.2 指定版本安装

```bash
# Linux x86_64 + Python 3.12
pip install tongagents==2.7.19 \
    --index-url https://nexus.mybigai.ac.cn/repository/pypi/simple/

# 跨平台源码安装（macOS / 未发布 wheel 的平台）
pip install tongagents==2.7.19 \
    --index-url https://nexus.mybigai.ac.cn/repository/pypi/simple/ \
    --no-binary :all:
```

### 3.3 依赖说明

`tongagents` 的运行时依赖包括：

- **LLM 栈**：`pydantic>=2.10.5`、`litellm==1.65.0`、`langchain-community`、`langchain-openai`、`langchain-ollama`
- **数据栈**：`pandas`、`pyarrow`、`pypdf`、`openpyxl`、`pymupdf`、`docx2txt`、`unstructured`、`bs4`、`xlrd`
- **服务栈**：`fastapi`、`uvicorn`、`boto3`、`aiobotocore`、`s3fs`、`fsspec`、`jinja2`、`httpx`、`sqlalchemy`、`psycopg2-binary`、`redis`
- **可观测性**：`opentelemetry-distro` + 多个 instrumentation 子包
- **MCP**：`mcp[cli]>=1.10.1,<1.27`
- **平台**：`tong-env>=0.1.0`（Nexus 私有包）

> 全部依赖会通过 pip 自动从 Nexus + PyPI 联合解析，无需手动处理。

---

## 4. 安装 CLI（tongagents-cli）

```bash
pip install --upgrade tongagents-cli
```

**当前最新版本**：`tongagents_cli-1.8.19`

CLI 额外依赖：`click`、`rich`、`prompt-toolkit`、`textual`、`pyyaml`、`croniter`、`mcp[cli]`、`python-dotenv`、`httpx`。

---

## 5. 安装 Lesson 2 依赖

Lesson 2 主要演示 **CoT / Self-Consistency / ToT / RAG / PromptTemplate** 等推理与检索模式，这些技术**不需要调用真实 LLM 端点**——它们基于 tongagents 的 `Agent` + `AgentSettings` 抽象，纯算法逻辑可被单元测试覆盖。

```bash
pip install -r requirements.txt
```

依赖说明：

- `tongagents>=2.7.19`：核心 SDK（Agent / AgentSettings / Workflow）
- `pytest>=7.4.0`：测试框架
- `pytest-asyncio>=0.23.0`：异步测试支持
- `python-dotenv>=1.0.0`：读取 .env

---

## 6. 验证安装

```bash
# 6.1 验证 Python 模块
python -c "import tongagents; print('tongagents', tongagents.__version__, tongagents.__file__)"

# 6.2 验证 CLI 可执行
tongagents --version
# 预期输出：tongagents-cli, version 1.8.19

# 6.3 验证 SDK 核心 API
python -c "
from tongagents.agent import Agent, AgentSettings
print('AgentSettings fields:', list(AgentSettings.model_fields.keys()))
"

# 6.4 跑 Lesson 2 全部测试
cd lesson2
python -m pytest tests/ -v
```

预期输出：

```
tongagents 2.7.19 /home/user/.venv/lib/python3.12/site-packages/tongagents/__init__.py
tongagents-cli, version 1.8.19
AgentSettings fields: ['name', 'description', 'capabilities', 'model', 'temperature', 'max_iterations', 'verbose', 'topic']
============================= test session starts ==============================
collected N items

tests/test_cot.py ........ [100%]
tests/test_self_consistency.py ...... [100%]
tests/test_tot.py ........ [100%]
tests/test_rag.py ...... [100%]
tests/test_prompt_template.py ........ [100%]
tests/test_cot_prompt_agent.py ........ [100%]

============================== N passed in X.XXs ===============================
```

---

## 7. 升级 / 卸载

```bash
# 升级到最新
pip install --upgrade tongagents tongagents-cli

# 查看本地版本
pip show tongagents
pip show tongagents-cli

# 卸载
pip uninstall tongagents tongagents-cli -y
```

---

## 8. 常见问题

### 8.1 找不到 tongagents 包

- 确认 `pip.conf` 配置了 Nexus 镜像
- 确认网络能访问 `https://nexus.mybigai.ac.cn/`
- 确认 Python 版本 >= 3.11

### 8.2 安装时报 `tong-env>=0.1.0 not found`

`tong-env` 是 BigAI 平台私有包，**仅在 Nexus 镜像中**。请确认 `index-url` 指向 Nexus，而不是 `pypi.org`。

### 8.3 wheel 与本地 Python ABI 不匹配

错误示例：`tongagents-2.7.19-cp312-cp312-linux_x86_64.whl is not a supported wheel on this platform.`

- 检查 Python 版本：`python -c "import sys; print(sys.version, sys.platform)"`
- 当前发布 wheel：**cp311 / cp312 / cp313**（Linux x86_64、Win amd64）
- 不支持：**Linux ARM64、macOS、Apple Silicon**（需用 `--no-binary :all:` 源码安装）

### 8.4 CLI 启动报 `ModuleNotFoundError`

执行 `pip install tongagents-cli` 会自动补齐 CLI 运行时依赖。无需额外手动安装。

---

## 9. 参考链接

- **Nexus 镜像根目录**：`https://nexus.mybigai.ac.cn/`
- **PyPI 简单索引**：`https://nexus.mybigai.ac.cn/repository/pypi/simple/`
- **tongagents 包索引**：`https://nexus.mybigai.ac.cn/repository/pypi/simple/tongagents/`
- **tongagents-cli 包索引**：`https://nexus.mybigai.ac.cn/repository/pypi/simple/tongagents-cli/`
- **课程仓库**：`https://github.com/temp-bigai/tongagents-course`
- **Lesson 1 安装文档**：[../lesson1/INSTALL.md](../lesson1/INSTALL.md)