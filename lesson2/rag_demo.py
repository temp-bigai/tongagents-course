"""
Lesson 2: RAG — Retrieval-Augmented Generation

RAG = 检索 (Retrieval) + 生成 (Generation)
    1. 把知识库切块、向量化、入库
    2. 用户提问时，检索 top-k 相关 chunk
    3. 把 chunk 作为 context 拼到 prompt，送给 LLM 生成

本示例演示：
1. 一个最小可用的内存 VectorStore（基于词袋 + cosine）
2. Retriever：检索 top-k
3. RAGAgent：检索 + 生成

运行方式：
    $ python rag_demo.py
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from collections.abc import AsyncIterator, Iterator
from typing import Any

from tongagents.agent import Agent, AgentSettings

from prompt_template import RAG_TEMPLATE


# ============================================================
# 1. AgentSettings：配置 RAG Agent
# ============================================================

RAG_AGENT_SETTINGS = AgentSettings(
    name="rag_agent",
    description="Retrieval-Augmented Generation — retrieve docs, then generate answer",
    capabilities=["rag", "retrieval", "generation"],
    model="gpt-4",
    temperature=0.0,
    max_iterations=1,
    verbose=False,
    topic="lesson2-rag",
    top_k=int(os.getenv("RAG_TOP_K", "3")),
)


# ============================================================
# 2. 内存向量存储（基于词袋 + 余弦相似度）
# ============================================================

_TOKEN_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """极简分词：英文按非字母数字切，中文按字切。"""
    text = text.lower()
    en = re.findall(r"[a-z0-9]+", text)
    cn = re.findall(r"[\u4e00-\u9fff]", text)
    return en + cn


def bow_vector(text: str) -> dict[str, float]:
    """词袋向量：term -> count。"""
    return dict(Counter(tokenize(text)))


def cosine(v1: dict[str, float], v2: dict[str, float]) -> float:
    """两个稀疏向量的余弦相似度。"""
    if not v1 or not v2:
        return 0.0
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in set(v1) & set(v2))
    n1 = math.sqrt(sum(x * x for x in v1.values()))
    n2 = math.sqrt(sum(x * x for x in v2.values()))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


class VectorStore:
    """一个最小内存版 VectorStore：支持 add / retrieve(top_k)。"""

    def __init__(self) -> None:
        self._docs: list[str] = []
        self._vecs: list[dict[str, float]] = []

    def add(self, doc: str) -> None:
        self._docs.append(doc)
        self._vecs.append(bow_vector(doc))

    def __len__(self) -> int:
        return len(self._docs)

    def retrieve(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """返回 top_k 最相似的文档。"""
        q_vec = bow_vector(query)
        scored = [
            (cosine(q_vec, v), d)
            for d, v in zip(self._docs, self._vecs)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]
        return [
            {"doc": d, "score": round(s, 4)}
            for s, d in top
        ]


# ============================================================
# 3. RAGAgent
# ============================================================

class RAGAgent(Agent):
    """RAG Agent：retrieve -> augment prompt -> generate。

    真实运行中 step() 会调用 self.llm.generate(prompt)；
    本示例的 _mock_generate() 用规则化回答演示 prompt 结构。
    """

    agent_setting = RAG_AGENT_SETTINGS
    rag_template = RAG_TEMPLATE

    def __init__(
        self,
        knowledge_base: list[str] | None = None,
        top_k: int | None = None,
        store: VectorStore | None = None,
    ) -> None:
        try:
            super().__init__(agent_setting=self.agent_setting)
        except TypeError:
            super().__init__()
        self.store = store or VectorStore()
        for doc in (knowledge_base or DEFAULT_KB):
            self.store.add(doc)
        self.top_k = top_k or self.agent_setting.top_k

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        return self.store.retrieve(query, top_k=self.top_k)

    def _mock_generate(self, prompt: dict[str, str]) -> str:
        """Mock 生成：从 prompt 的 context 里摘第一个句子作为答案。"""
        ctx = prompt["user"].split("Context:\n", 1)[-1].split("\n\nQuestion:", 1)[0]
        first_line = ctx.strip().split("\n", 1)[0]
        return f"Based on the context: {first_line}"

    def step(self, event: Any) -> dict[str, Any]:
        if not isinstance(event, str):
            event = str(event)
        retrieved = self.retrieve(event)
        context = "\n".join(r["doc"] for r in retrieved)
        prompt = self.rag_template.format(context=context, question=event)
        answer = self._mock_generate(prompt)
        return {
            "question": event,
            "retrieved": retrieved,
            "prompt": prompt,
            "answer": answer,
        }

    def run(self, events: Iterator[Any]) -> Iterator[dict[str, Any]]:
        for event in events:
            yield self.step(event)

    async def astep(self, event: Any) -> dict[str, Any]:
        return self.step(event)

    async def arun(self, events: AsyncIterator[Any] | Any) -> AsyncIterator[dict[str, Any]]:
        if hasattr(events, "__aiter__"):
            async for event in events:
                yield await self.astep(event)
        else:
            for event in events:
                yield await self.astep(event)


# ============================================================
# 4. 默认知识库（演示用）
# ============================================================

DEFAULT_KB = [
    "TongAgents is a multi-agent framework by BigAI.",
    "TongAgents 2.7.19 ships as a Cython-encrypted wheel from BigAI Nexus.",
    "CoT stands for Chain-of-Thought, a prompting technique that improves reasoning.",
    "RAG stands for Retrieval-Augmented Generation, combining retrieval with generation.",
    "Self-Consistency samples multiple CoT paths and votes for the most consistent answer.",
    "Tree of Thoughts explores multiple branches and prunes low-scoring paths.",
    "EchoAgent from lesson1 simply echoes back the input with a prefix.",
    "Lesson 2 introduces pre-agent era techniques: CoT, Self-Consistency, ToT, RAG.",
]


# ============================================================
# 5. 演示
# ============================================================

def demo_vector_store():
    """演示 VectorStore 的 add + retrieve。"""
    print("=== demo_vector_store ===")
    store = VectorStore()
    for doc in DEFAULT_KB:
        store.add(doc)
    print(f"total docs = {len(store)}")
    results = store.retrieve("What is CoT?", top_k=2)
    for r in results:
        print(f"  [{r['score']}] {r['doc']}")
    print()


def demo_rag_agent():
    """完整 RAG 演示。"""
    print("=== demo_rag_agent ===")
    agent = RAGAgent(top_k=2)
    result = agent.step("What is RAG?")
    print(f"question = {result['question']}")
    print(f"retrieved = {[r['doc'][:40] + '...' for r in result['retrieved']]}")
    print(f"answer   = {result['answer']}")
    print()


def demo_settings_inspect():
    """检查 AgentSettings。"""
    print("=== demo_settings_inspect ===")
    print("name     =", RAG_AGENT_SETTINGS.name)
    print("topic    =", RAG_AGENT_SETTINGS.topic)
    print("top_k    =", RAG_AGENT_SETTINGS.top_k)
    print()


# ============================================================

def main() -> None:
    demo_settings_inspect()
    demo_vector_store()
    demo_rag_agent()


if __name__ == "__main__":
    main()