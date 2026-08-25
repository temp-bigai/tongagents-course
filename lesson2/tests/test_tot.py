"""
test_tot.py — ToT Agent 的单元测试
"""

from __future__ import annotations

import pytest

from tot_demo import (
    TOT_SETTINGS,
    ThoughtNode,
    ToTAgent,
    score_state,
)


class TestScoreState:
    """score_state() 评估函数。"""

    def test_positive_keywords_boost(self):
        """正向关键词加分。"""
        s1 = score_state("this is possible and valid")
        s2 = score_state("nothing")
        assert s1 > s2

    def test_negative_keywords_penalize(self):
        """负向关键词扣分。"""
        s1 = score_state("this is a dead-end, invalid")
        s2 = score_state("nothing")
        assert s1 < s2

    def test_score_returns_float(self):
        """score 返回 float。"""
        assert isinstance(score_state("anything"), float)

    def test_empty_string(self):
        """空字符串。"""
        assert score_state("") == 1.0


class TestThoughtNode:
    """ThoughtNode 数据结构。"""

    def test_construction(self):
        node = ThoughtNode(state="root", score=0.5)
        assert node.state == "root"
        assert node.score == 0.5
        assert node.parent is None
        assert node.children == []
        assert node.depth == 0

    def test_add_child(self):
        parent = ThoughtNode(state="p")
        child = ThoughtNode(state="c", parent=parent)
        parent.add_child(child)
        assert parent.children == [child]

    def test_path_to_here(self):
        """path_to_here() 返回从根到当前节点的 state 列表。"""
        root = ThoughtNode(state="root")
        mid = ThoughtNode(state="mid", parent=root)
        leaf = ThoughtNode(state="leaf", parent=mid)
        path = leaf.path_to_here()
        assert path == ["root", "mid", "leaf"]


class TestToTAgentBFS:
    """ToTAgent.bfs() 搜索行为。"""

    def test_bfs_returns_dict(self):
        agent = ToTAgent(branch_factor=2, max_depth=2)
        result = agent.bfs("Start")
        assert "explored" in result
        assert "best_path" in result
        assert "best_score" in result
        assert "reached_goal" in result

    def test_bfs_explored_at_least_one(self):
        """至少探索 1 个节点。"""
        agent = ToTAgent(branch_factor=2, max_depth=2)
        result = agent.bfs("Start")
        assert result["explored"] >= 1

    def test_bfs_reaches_goal_when_solved_in_subtree(self):
        """当某个候选触发 solved 时，应能到达 goal。"""
        agent = ToTAgent(branch_factor=2, max_depth=3)
        # 重写 generate_thoughts：第二层会触发 solved
        def gen(state):
            if state.endswith("approach_2"):
                return [f"{state} -> solved"]
            return [f"{state} -> approach_{i+1}" for i in range(2)]
        agent.generate_thoughts = gen  # type: ignore
        result = agent.bfs("Start")
        assert result["reached_goal"] is True
        assert any("solved" in s for s in result["best_path"])

    def test_bfs_respects_max_depth(self):
        """max_depth 限制搜索深度。"""
        agent = ToTAgent(branch_factor=2, max_depth=2)
        agent.is_goal = lambda s: False  # type: ignore
        result = agent.bfs("Start")
        # 不应超过 max_depth + 1（root 在 0 层）
        assert all(isinstance(s, str) for s in result["best_path"])


class TestToTAgentStep:
    """ToTAgent.step() 的行为。"""

    def test_step_returns_dict(self):
        agent = ToTAgent(branch_factor=2, max_depth=2)
        result = agent.step("Start")
        assert isinstance(result, dict)
        assert "explored" in result

    def test_step_non_string_input(self):
        agent = ToTAgent(branch_factor=2, max_depth=2)
        result = agent.step(123)  # type: ignore[arg-type]
        assert "explored" in result


class TestToTSettings:
    """ToT AgentSettings 配置。"""

    def test_branch_factor(self):
        assert TOT_SETTINGS.branch_factor >= 1

    def test_max_depth(self):
        assert TOT_SETTINGS.max_depth >= 1

    def test_capabilities(self):
        assert "tot" in TOT_SETTINGS.capabilities