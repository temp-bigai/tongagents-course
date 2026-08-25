"""
test_cot.py — CoT Agent 的单元测试
"""

from __future__ import annotations

import pytest

from cot_demo import CoTAgent, COT_AGENT_SETTINGS, parse_cot_response
from prompt_template import COT_TEMPLATE


class TestCotTemplate:
    """CoT PromptTemplate 的结构。"""

    def test_cot_template_contains_step_by_step(self):
        """CoT template 必含 'think step by step'。"""
        rendered = COT_TEMPLATE.format(question="x")
        assert "step by step" in rendered["user"].lower()
        assert "Final Answer" in rendered["user"]

    def test_cot_template_has_5_steps(self):
        """CoT template 至少包含 5 个 Step。"""
        rendered = COT_TEMPLATE.format(question="x")
        for i in range(1, 6):
            assert f"Step {i}" in rendered["user"]


class TestParseCotResponse:
    """parse_cot_response() 的解析行为。"""

    def test_parse_full_response(self):
        """完整响应：5 steps + final answer。"""
        resp = (
            "Step 1: A\n"
            "Step 2: B\n"
            "Step 3: C\n"
            "Step 4: D\n"
            "Step 5: E\n"
            "\n"
            "Final Answer: hello"
        )
        parsed = parse_cot_response(resp)
        assert len(parsed["reasoning_steps"]) == 5
        assert parsed["final_answer"] == "hello"

    def test_parse_missing_final(self):
        """缺 Final Answer 时 final_answer 为 None。"""
        resp = "Step 1: A\nStep 2: B"
        parsed = parse_cot_response(resp)
        assert parsed["reasoning_steps"] == ["A", "B"]
        assert parsed["final_answer"] is None

    def test_parse_empty(self):
        """空响应。"""
        parsed = parse_cot_response("")
        assert parsed["reasoning_steps"] == []
        assert parsed["final_answer"] is None

    def test_parse_with_chinese_colon(self):
        """中文冒号 Step 1：A 也能匹配。"""
        resp = "Step 1：A\nFinal Answer：B"
        parsed = parse_cot_response(resp)
        assert parsed["reasoning_steps"] == ["A"]
        assert parsed["final_answer"] == "B"


class TestCotAgentStep:
    """CoTAgent.step() 的行为。"""

    def test_step_returns_dict(self):
        """step() 返回 dict，含 reasoning_steps + final_answer。"""
        agent = CoTAgent(agent_setting=COT_AGENT_SETTINGS)
        result = agent.step("If 3 apples cost $6, how much do 10 apples cost?")
        assert isinstance(result, dict)
        assert "reasoning_steps" in result
        assert "final_answer" in result

    def test_step_apple_question(self):
        """苹果问题：final_answer 应为 $20。"""
        agent = CoTAgent(agent_setting=COT_AGENT_SETTINGS)
        result = agent.step("If 3 apples cost $6, how much do 10 apples cost?")
        assert result["final_answer"] == "$20"
        assert len(result["reasoning_steps"]) >= 4

    def test_step_train_question(self):
        """火车问题：final_answer 应为 120 miles。"""
        agent = CoTAgent(agent_setting=COT_AGENT_SETTINGS)
        result = agent.step("A train travels 60 mph for 2 hours. How far?")
        assert result["final_answer"] == "120 miles"
        assert len(result["reasoning_steps"]) >= 4

    def test_step_non_string_input(self):
        """非字符串输入也能 step（str 强转）。"""
        agent = CoTAgent(agent_setting=COT_AGENT_SETTINGS)
        result = agent.step(123)  # type: ignore[arg-type]
        assert "reasoning_steps" in result


class TestCotAgentRun:
    """CoTAgent.run() 流式行为。"""

    def test_run_yields_per_event(self):
        """run() 对每条 event 产出一个 result。"""
        agent = CoTAgent(agent_setting=COT_AGENT_SETTINGS)
        questions = ["If 3 apples cost $6, how much do 10 apples cost?",
                     "A train travels 60 mph for 2 hours. How far?"]
        results = list(agent.run(iter(questions)))
        assert len(results) == 2
        assert results[0]["final_answer"] == "$20"
        assert results[1]["final_answer"] == "120 miles"


class TestCotAgentSettings:
    """CoT AgentSettings 配置。"""

    def test_temperature_zero(self):
        """CoT 通常 temperature=0 保证稳定。"""
        assert COT_AGENT_SETTINGS.temperature == 0.0

    def test_capabilities(self):
        """capabilities 含 cot。"""
        assert "cot" in COT_AGENT_SETTINGS.capabilities