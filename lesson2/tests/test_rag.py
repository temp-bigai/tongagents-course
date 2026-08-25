"""
test_rag.py — RAG Agent 的单元测试
"""

from __future__ import annotations

import math

import pytest

from rag_demo import (
    DEFAULT_KB,
    RAG_AGENT_SETTINGS,
    RAGAgent,
    VectorStore,
    bow_vector,
    cosine,
    tokenize,
)


class TestTokenize:
    """tokenize() 分词。"""

    def test_english(self):
        """英文分词。"""
        assert "hello" in tokenize("Hello World")

    def test_chinese(self):
        """中文逐字。"""
        tokens = tokenize("你好世界")
        assert set(tokens) >= {"你", "好", "世", "界"}


class TestBowAndCosine:
    """bow_vector + cosine。"""

    def test_bow_counts(self):
        vec = bow_vector("a a b")
        assert vec == {"a": 2, "b": 1}

    def test_cosine_identical(self):
        """相同向量余弦 = 1。"""
        v = bow_vector("hello world")
        assert cosine(v, v) == pytest.approx(1.0)

    def test_cosine_disjoint(self):
        """无交集余弦 = 0。"""
        a = bow_vector("foo")
        b = bow_vector("bar")
        assert cosine(a, b) == 0.0

    def test_cosine_partial(self):
        """部分重叠。"""
        a = bow_vector("a b c")
        b = bow_vector("a b d")
        # cos = (1+1)/(sqrt(3)*sqrt(3)) = 2/3
        assert cosine(a, b) == pytest.approx(2 / 3)

    def test_cosine_empty(self):
        """空向量。"""
        assert cosine({}, {"x": 1}) == 0.0
        assert cosine({"x": 1}, {}) == 0.0


class TestVectorStore:
    """VectorStore.add / retrieve。"""

    def test_add_and_len(self):
        store = VectorStore()
        assert len(store) == 0
        store.add("doc1")
        store.add("doc2")
        assert len(store) == 2

    def test_retrieve_returns_top_k(self):
        store = VectorStore()
        store.add("apple banana")
        store.add("apple apple")
        store.add("zebra")
        results = store.retrieve("apple", top_k=2)
        assert len(results) == 2
        assert all("score" in r and "doc" in r for r in results)

    def test_retrieve_top_k_ranks_by_relevance(self):
        """最相关的排第一。"""
        store = VectorStore()
        store.add("zebra zebra zebra")  # 不相关
        store.add("apple apple apple")  # 完全匹配
        store.add("banana")             # 不相关
        results = store.retrieve("apple", top_k=3)
        assert "apple" in results[0]["doc"]


class TestRagAgentStep:
    """RAGAgent.step() 的行为。"""

    def test_step_returns_dict(self):
        agent = RAGAgent(top_k=2)
        result = agent.step("What is RAG?")
        assert "question" in result
        assert "retrieved" in result
        assert "prompt" in result
        assert "answer" in result

    def test_step_retrieves_top_k_docs(self):
        agent = RAGAgent(top_k=3)
        result = agent.step("What is CoT?")
        assert len(result["retrieved"]) <= 3

    def test_step_uses_default_kb(self):
        """默认 KB 应被加载。"""
        agent = RAGAgent(top_k=3)
        assert len(agent.store) >= 1

    def test_step_custom_kb(self):
        """自定义 KB。"""
        agent = RAGAgent(knowledge_base=["foo", "bar"], top_k=1)
        assert len(agent.store) == 2
        result = agent.step("foo")
        assert result["retrieved"][0]["doc"] == "foo"

    def test_step_non_string_input(self):
        agent = RAGAgent(top_k=2)
        result = agent.step(123)  # type: ignore[arg-type]
        assert "answer" in result


class TestRagAgentRun:
    """RAGAgent.run() 流式。"""

    def test_run_yields_one_per_event(self):
        agent = RAGAgent(top_k=2)
        results = list(agent.run(iter(["q1", "q2"])))
        assert len(results) == 2


class TestRagSettings:
    """RAG AgentSettings 配置。"""

    def test_top_k(self):
        assert RAG_AGENT_SETTINGS.top_k >= 1

    def test_capabilities(self):
        assert "rag" in RAG_AGENT_SETTINGS.capabilities


class TestDefaultKB:
    """DEFAULT_KB 内容。"""

    def test_kb_non_empty(self):
        assert len(DEFAULT_KB) >= 3

    def test_kb_mentions_rag(self):
        """KB 应至少有一篇提到 RAG。"""
        assert any("RAG" in doc or "rag" in doc for doc in DEFAULT_KB)