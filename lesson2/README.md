# Lesson 2 — 前 Agent 时期技术：CoT + RAG + PromptTemplate

> 在 Lesson 1 中，我们学会了用 `tongagents` SDK 写出第一个 Echo Agent。
> 本课聚焦 **大模型时代的前 Agent 时期技术**：它们是后续 Agent 模式的根基。

---

## 🎯 学习目标

完成本课后，你将掌握：

1. ✅ 从**本地 wheel** 安装 TongAgents SDK（**不依赖 BigAI Nexus**）
2. ✅ **Prompt Engineering 的 6 阶段演进**（Zero-shot → Few-shot → CoT → Self-Consistency → ToT → RAG）
3. ✅ **CoT（Chain-of-Thought）**：用 step-by-step prompt 提升推理能力
4. ✅ **Self-Consistency**：多路径采样 + 投票
5. ✅ **ToT（Tree of Thoughts）**：树形搜索 + 评估剪枝
6. ✅ **RAG（Retrieval-Augmented Generation）**：检索 + 生成
7. ✅ **PromptTemplate**：把 prompt 抽象成可复用模板
8. ✅ 用 tongagents SDK 的 `Agent` + `AgentSettings` 实现"CoT Prompt Agent"（PPT Slide 43）

---

## 📂 目录结构

```
lesson2/
├── README.md                 # 本文件（课程主入口）
├── INSTALL.md                # 详细安装文档（本地 wheel 方式）
├── pyproject.toml            # Python 项目配置（不含 nexus）
├── requirements.txt          # Python 依赖清单
├── .env.example              # 环境变量模板
├── .gitignore                # Python/venv/db 忽略
├── prompt_template.py        # PromptTemplate 抽象（基础）
├── cot_demo.py               # CoT 主示例（Echo → CoT）
├── cot_self_consistency.py   # Self-Consistency（多路径采样 + 投票）
├── tot_demo.py               # ToT（Tree of Thoughts 树形搜索）
├── rag_demo.py               # RAG（检索 + 生成）
├── cot_prompt_agent.py       # CoT Prompt Agent（PPT Slide 43）
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_prompt_template.py
    ├── test_cot.py
    ├── test_self_consistency.py
    ├── test_tot.py
    ├── test_rag.py
    └── test_cot_prompt_agent.py
```

> 💡 **`wheels/` 目录**: 本课程 3 个示例（`cli-sample/`、`lesson1/`、`lesson2/`）共用同一份
> wheel 文件, 放在**仓库根目录**的 `wheels/` 下。

---

## 🚀 快速开始

### 1. 准备 wheels（一次性）

```bash
# 从项目维护者获取 wheel 文件, 放到仓库根目录 wheels/
cd tongagents-course
ls ../wheels/
# 期望看到 tongagents-*.whl + tongagents_cli-*.whl (各 1 个或 2 个)
```

### 2. 安装（5 分钟）

参考 [INSTALL.md](./INSTALL.md) 详细步骤。TL;DR：

```bash
cd lesson2
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# 装本地 wheel (不走 nexus, 不走 [tool.uv.sources])
pip install ../wheels/tongagents-*.whl
pip install ../wheels/tongagents_cli-*.whl

# 装 lesson2 依赖
pip install -e .
```

### 3. 跑 6 个示例

```bash
# 3.1 PromptTemplate 基础
python prompt_template.py

# 3.2 CoT Demo（Echo → CoT 升级）
python cot_demo.py

# 3.3 Self-Consistency（多路径采样 + 投票）
python cot_self_consistency.py

# 3.4 ToT（树形搜索）
python tot_demo.py

# 3.5 RAG（检索 + 生成）
python rag_demo.py

# 3.6 CoT Prompt Agent（PPT Slide 43）
python cot_prompt_agent.py
```

### 4. 跑测试

```bash
python -m pytest tests/ -v
```

---

## 📚 课程大纲

### 1. Prompt Engineering 的 6 阶段演进

| 阶段 | 技术 | 关键 idea | 示例文件 |
|---|---|---|---|
| 1 | **Zero-shot** | 直接提问 | `prompt_template.ZERO_SHOT_TEMPLATE` |
| 2 | **Few-shot** | 给几个示例让模型"类比" | `prompt_template.FEW_SHOT_TEMPLATE` |
| 3 | **CoT** | "Let's think step by step" | `cot_demo.py` |
| 4 | **Self-Consistency** | 多次 CoT + 投票 | `cot_self_consistency.py` |
| 5 | **ToT** | 树形搜索 + 评估剪枝 | `tot_demo.py` |
| 6 | **RAG** | 检索知识库 + 生成 | `rag_demo.py` |

### 2. CoT 基础

```python
from cot_demo import CoTAgent, COT_AGENT_SETTINGS

agent = CoTAgent(agent_setting=COT_AGENT_SETTINGS)
result = agent.step("If 3 apples cost $6, how much do 10 apples cost?")
# {
#   "reasoning_steps": ["Step 1: ...", ..., "Step 5: ..."],
#   "final_answer": "$20",
#   "raw_response": "Step 1: ...\nFinal Answer: $20"
# }
```

### 3. Self-Consistency（多路径采样 + 投票）

```python
from cot_self_consistency import SelfConsistencyAgent

agent = SelfConsistencyAgent(n_samples=5)
result = agent.step("If 3 apples cost $6, how much do 10 apples cost?")
# {
#   "samples": ["$20", "$20", "$20", "$18", "$22"],
#   "winner": "$20",
#   "vote_count": 3,
#   "vote_ratio": 0.6,
# }
```

### 4. ToT（Tree of Thoughts 树形搜索）

```python
from tot_demo import ToTAgent

agent = ToTAgent(branch_factor=3, max_depth=4)
result = agent.step("Start")
# {
#   "explored": 13,
#   "best_path": ["Start", "...approach_2", "...solved"],
#   "reached_goal": True,
# }
```

### 5. RAG（检索 + 生成）

```python
from rag_demo import RAGAgent

agent = RAGAgent(top_k=3)
result = agent.step("What is RAG?")
# {
#   "retrieved": [{"doc": "RAG stands for ...", "score": 0.92}, ...],
#   "prompt": "Context: ...\n\nQuestion: What is RAG?\n\nAnswer:",
#   "answer": "Based on the context: RAG stands for ...",
# }
```

### 6. PromptTemplate 抽象

```python
from prompt_template import PromptTemplate

tpl = PromptTemplate(
    system="You are an expert who thinks step by step.",
    user="Question: {question}\nLet's think step by step.",
)
rendered = tpl.format(question="What is 1+1?")
# {"system": "...", "user": "Question: What is 1+1?\nLet's think step by step."}

# 部分绑定
p = tpl.partial()  # 不绑定也支持
```

### 7. 实战：CoT Prompt Agent（PPT Slide 43 完整实现）

```python
from cot_prompt_agent import CoTPromptAgent

agent = CoTPromptAgent()
result = agent.step("A train travels 60 mph for 2 hours. How far?")
# {
#   "reasoning_steps": [
#     "Identify what we know. Speed = 60 mph, time = 2 hours.",
#     "Identify what we need to find. Distance traveled.",
#     "Apply relevant knowledge. distance = speed * time.",
#     "Calculate. 60 mph * 2 h = 120 miles.",
#     "Verify. 120 miles = 60 mph * 2 h, consistent.",
#   ],
#   "final_answer": "120 miles",
# }
```

### 8. 作业：实现 CoT Prompt Agent

1. 给 `cot_prompt_agent.py` 加一个 `_call_llm()` 方法，**真实调用** `self.llm.generate(prompt)`
2. 加一个 `test_llm_integration.py`（mock LLM）
3. 提交到 GitHub

---

## 🧪 测试覆盖

```bash
$ python -m pytest tests/ -v
```

| 测试文件 | 覆盖范围 |
|---|---|
| `test_prompt_template.py` | PromptTemplate 基础 / partial / AgentSettings 集成 |
| `test_cot.py` | CoT Agent 推理、步骤解析、AgentSettings |
| `test_self_consistency.py` | 投票逻辑、N 次采样、流式处理 |
| `test_tot.py` | score_state、ThoughtNode、BFS、AgentSettings |
| `test_rag.py` | tokenize / bow_vector / cosine / VectorStore / RAGAgent |
| `test_cot_prompt_agent.py` | CoT Prompt Agent 类属性 / step / run / AgentSettings |

---

## 🔑 核心要点

### CoT vs Echo Agent

```
EchoAgent.step("hello")
    → "Echo: hello"                          (1 步)

CoTPromptAgent.step("If 3 apples cost $6, how much do 10 apples cost?")
    → {reasoning_steps: [...5 步...], final_answer: "$20"}    (N 步)
```

CoT 的本质：**用 prompt 引导 LLM "思考过程可见"，而非直接给答案**。

### Self-Consistency 的本质

**多次采样 + 多数投票**。温度 T > 0 让模型给出不同路径，多数答案更可能正确。

### ToT vs CoT

```
CoT:  Q → step1 → step2 → ... → answer       (线性链)
ToT:  Q → [b1, b2, b3] → 评估 → 剪枝 → 扩展    (树形搜索)
```

ToT 给每个状态打分，保留高分分支，剪掉低分分支。

### RAG 的本质

```
Q → [检索 top-k 文档] → context + Q → LLM → A
```

把"知识"外置到向量库，模型只负责"用 context 回答问题"。

---

## 🛠 常见问题

### Q: 为什么用本地 wheel 而不是 Nexus？

A: **开发者通常无 BigAI 内网访问权限**。改用本地 wheel 后, 整个安装流程**完全离线**,
不依赖 Nexus 凭据 / `~/.config/pip/pip.conf` / `[tool.uv.sources]` editable 源。
课程维护者负责构建 + 分发 wheel, 开发者只负责 `pip install ./wheels/*.whl`。

### Q: PromptTemplate 一定要 dataclass 吗？

A: 本课选 dataclass 是因为：
- 简单（不用装 jinja2）
- `__post_init__` 自动提取必填变量
- 可以序列化（JSON / YAML）

真实生产里常用 [jinja2](https://palletsprojects.com/p/jinja/) 或 [LangChain 的 PromptTemplate](https://python.langchain.com/docs/modules/model_io/prompts/)。

### Q: Self-Consistency 为什么能 work？

A: 多路径独立采样时，每条路径可能错，但**多数正确**。这跟集成学习的 bagging 思路类似。

### Q: ToT 是不是过度工程？

A: 取决于问题复杂度：
- 简单问答：CoT 够用
- 数学 / 规划 / 决策：ToT 能显著提升
- 代价：API 调用 N×branch×depth 次

### Q: RAG 的 VectorStore 我能用生产级的吗？

A: 本课是教学用内存版。生产推荐：
- **嵌入模型**：`text-embedding-3-small`（OpenAI）/ `bge-large-zh`（开源中文）
- **向量库**：Chroma / Milvus / Pinecone / Weaviate

---

## 📚 下一步

- **Lesson 3**：LLM Agent 模式（ReAct / Plan-and-Execute）
- **Lesson 4**：Multi-Agent 协作
- **选修 2**：把 CoT Agent 接入 Vector DB

---

## 📖 参考资料

- [INSTALL.md](./INSTALL.md) — 详细安装文档（本地 wheel 方式）
- [tongagents-course 仓库](https://github.com/temp-bigai/tongagents-course)
- [Wei et al. (2022) — Chain-of-Thought Prompting](https://arxiv.org/abs/2201.11903)
- [Wang et al. (2022) — Self-Consistency](https://arxiv.org/abs/2203.11171)
- [Yao et al. (2023) — Tree of Thoughts](https://arxiv.org/abs/2305.10601)
- [Lewis et al. (2020) — Retrieval-Augmented Generation](https://arxiv.org/abs/2005.11401)
