# TongAgents Course

智能体实践课程代码库（从 TongAgent 到 OpenClaw）

11 个 Lesson · 8 个核心 + 3 个选修 + 1 个贯穿大作业

---

## 🚀 快速开始（开发者，本地 wheel 方式）

> **v0.2.0 重要变更**: 本课程**不依赖 BigAI Nexus 内网**。开发者只需要拿到项目维护者
> 提供的 2 个本地 wheel 文件, 用 `pip install ./wheels/*.whl` 即可, 完全离线安装。

### 一次性准备 wheels 目录

```bash
cd tongagents-course    # 仓库根目录
mkdir -p wheels
cp /path/to/tongagents-*.whl wheels/
cp /path/to/tongagents_cli-*.whl wheels/

ls -lh wheels/
# 期望看到 (优先 cp312-cp312-linux_x86_64 小包):
# tongagents-2.7.21-cp312-cp312-linux_x86_64.whl       (16M, Linux x86_64 推荐)
# tongagents_cli-1.8.22-cp312-cp312-linux_x86_64.whl   (5.1M, Linux x86_64 推荐)
# (可选) tongagents-2.7.21-py3-none-any.whl            (38M, 跨平台)
# (可选) tongagents_cli-1.8.22-py3-none-any.whl        (7.8M, 跨平台)
```

### 跑任一示例

```bash
# 方式 A: cli-sample (REPL + 6 个本地工具)
cd cli-sample
python3 -m venv .venv && source .venv/bin/activate
pip install ../wheels/tongagents-*.whl ../wheels/tongagents_cli-*.whl
pip install -e .
python cli_sample.py

# 方式 B: lesson1 (3 个示例 + 32 测试)
cd lesson1
python3 -m venv .venv && source .venv/bin/activate
pip install ../wheels/tongagents-*.whl ../wheels/tongagents_cli-*.whl
pip install -e .
python echo_agent.py
python agent_settings_demo.py
python node_declare_demo.py
python -m pytest tests/ -v

# 方式 C: lesson2 (6 个示例 + 87 测试)
cd lesson2
python3 -m venv .venv && source .venv/bin/activate
pip install ../wheels/tongagents-*.whl ../wheels/tongagents_cli-*.whl
pip install -e .
python prompt_template.py
python cot_demo.py
python cot_self_consistency.py
python tot_demo.py
python rag_demo.py
python cot_prompt_agent.py
python -m pytest tests/ -v
```

每个 lesson 的详细步骤见各自的 `INSTALL.md`。

---

## 课程结构

| Lesson | 主题 | 内容 |
|---|---|---|
| 01 | Agent 基本概念 | 演进 · 分类 · 循环 |
| 02 | 前 Agent 时期技术 | CoT · RAG |
| 03 | LLM API / TongAgents | SDK · CLI |
| 04 | 工具使用 / MCP / Sandbox | Function Call |
| 05 | ReAct 等经典范式 | Plan · Reflect |
| 06 | 记忆与 RAG 检索 | Vector · KG |
| 07 | 多智能体 / A2A / ANP | 协作 · 网络 |
| 08 | 评测与自演进 | Harness |
| 选修 | 安全 · 多模态 · 行业应用 | - |
| 大作业 | OpenClaw 多智能体项目 | - |

## TongAgents 示例

所有从 PPT 提取的 TongAgents SDK 代码按课程主题整理于各 lesson 目录。PPT 中明确出现的 SDK 代码集中在 Lesson 1、Lesson 2 和课程作业示例；其余 lesson 目录提供对应目录结构和 README，说明课程主题与后续扩展入口。

Lesson 4 已提供可执行 Notebook，详见 [`lesson4/README.md`](lesson4/README.md)。

## 安装方式对比

| 方案 | 优点 | 缺点 | 适用 |
|---|---|---|---|
| **本地 wheel (本课程默认)** | 离线 / 无 Nexus 凭据 / 跨环境一致 | 需维护者分发 wheel | 外部开发者 |
| Nexus pip.conf | 自动解析依赖 | 需内网 + 凭据 | 内部开发者 |
| `[tool.uv.sources]` editable | 调试方便 | 需 uv + 内网 + 编辑源 | Tong-Agent 维护者 |

---

## 致谢

基于 Tong-Agent SDK 2.4.0+（https://github.com/temp-bigai/Tong-Agent）
