"""
test_self_consistency.py — Self-Consistency Agent 的单元测试
"""

from __future__ import annotations

import pytest

from cot_self_consistency import SELF_CONSISTENCY_SETTINGS, SelfConsistencyAgent


class TestVote:
    """vote() 工具方法。"""

    def test_vote_majority(self):
        """多数获胜。"""
        agent = SelfConsistencyAgent(n_samples=5)
        answers = ["A", "B", "A", "A", "C"]
        winner, count = agent.vote(answers)
        assert winner == "A"
        assert count == 3

    def test_vote_all_same(self):
        """全部相同。"""
        agent = SelfConsistencyAgent(n_samples=4)
        answers = ["X", "X", "X", "X"]
        winner, count = agent.vote(answers)
        assert winner == "X"
        assert count == 4

    def test_vote_empty_raises(self):
        """空列表抛 ValueError。"""
        agent = SelfConsistencyAgent(n_samples=5)
        with pytest.raises(ValueError):
            agent.vote([])

    def test_vote_tie(self):
        """平票时取字典序最小的。"""
        agent = SelfConsistencyAgent(n_samples=2)
        answers = ["B", "A"]
        winner, _ = agent.vote(answers)
        assert winner == "A"  # 'A' < 'B'


class TestSelfConsistencyStep:
    """SelfConsistencyAgent.step() 的行为。"""

    def test_step_returns_dict(self):
        """step() 返回完整 dict。"""
        agent = SelfConsistencyAgent(n_samples=3)
        result = agent.step("If 3 apples cost $6, how much do 10 apples cost?")
        assert "question" in result
        assert "samples" in result
        assert "winner" in result
        assert "vote_count" in result
        assert "vote_ratio" in result

    def test_step_n_samples(self):
        """samples 长度等于 n_samples。"""
        n = 7
        agent = SelfConsistencyAgent(n_samples=n)
        result = agent.step("foo")
        assert len(result["samples"]) == n

    def test_step_vote_ratio_bounds(self):
        """vote_ratio ∈ [0, 1]。"""
        agent = SelfConsistencyAgent(n_samples=5)
        result = agent.step("bar")
        assert 0 <= result["vote_ratio"] <= 1

    def test_step_reasoning_steps_per_sample(self):
        """reasoning_steps_per_sample 是 list of lists。"""
        agent = SelfConsistencyAgent(n_samples=3)
        result = agent.step("baz")
        per = result["reasoning_steps_per_sample"]
        assert isinstance(per, list)
        assert len(per) == 3
        for steps in per:
            assert isinstance(steps, list)


class TestSelfConsistencyRun:
    """SelfConsistencyAgent.run() 流式行为。"""

    def test_run_yields_one_per_event(self):
        agent = SelfConsistencyAgent(n_samples=2)
        events = iter(["a", "b", "c"])
        results = list(agent.run(events))
        assert len(results) == 3


class TestSelfConsistencySettings:
    """Self-Consistency AgentSettings 配置。"""

    def test_n_samples_default(self):
        """AgentSettings.n_samples 默认值。"""
        assert SELF_CONSISTENCY_SETTINGS.n_samples >= 1

    def test_temperature_for_diversity(self):
        """Self-Consistency 通常 temperature > 0。"""
        # 允许 =0 也行，但默认 =0.7
        assert SELF_CONSISTENCY_SETTINGS.temperature >= 0

    def test_capabilities(self):
        """capabilities 含 self-consistency。"""
        assert "self-consistency" in SELF_CONSISTENCY_SETTINGS.capabilities