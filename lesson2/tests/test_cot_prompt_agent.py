"""
test_cot_prompt_agent.py — CoT Prompt Agent (PPT Slide 43) 的单元测试
"""

from __future__ import annotations

import pytest

from cot_prompt_agent import (
    COT_PROMPT_AGENT_SETTINGS,
    COT_REASONING_TEMPLATE,
    CoTPromptAgent,
    parse_cot_response,
)
from prompt_template import COT_TEMPLATE


class TestCotReasoningTemplate:
    """CoT Reasoning PromptTemplate 结构。"""

    def test_template_requires_question(self):
        assert "question" in COT_REASONING_TEMPLATE.required_vars

    def test_template_has_step_by_step(self):
        rendered = COT_REASONING_TEMPLATE.format(question="x")
        assert "step by step" in rendered["user"].lower()

    def test_template_has_final_answer_placeholder(self):
        rendered = COT_REASONING_TEMPLATE.format(question="x")
        assert "Final Answer" in rendered["user"]


class TestCoTPromptAgentStep:
    """CoTPromptAgent.step() 行为。"""

    def test_step_returns_dict(self):
        agent = CoTPromptAgent()
        result = agent.step("foo")
        assert isinstance(result, dict)
        assert "reasoning_steps" in result
        assert "final_answer" in result
        assert "raw_response" in result

    def test_step_apple(self):
        agent = CoTPromptAgent()
        result = agent.step("If 3 apples cost $6, how much do 10 apples cost?")
        assert result["final_answer"] == "$20"

    def test_step_train(self):
        agent = CoTPromptAgent()
        result = agent.step("A train travels 60 mph for 2 hours. How far?")
        assert result["final_answer"] == "120 miles"

    def test_step_with_llm_kwarg(self):
        """step() 支持传 llm 参数构造。"""
        agent = CoTPromptAgent(llm=None)
        result = agent.step("foo")
        assert "final_answer" in result

    def test_step_non_string_input(self):
        agent = CoTPromptAgent()
        result = agent.step(42)  # type: ignore[arg-type]
        assert "reasoning_steps" in result


class TestCoTPromptAgentRun:
    """CoTPromptAgent.run() 流式。"""

    def test_run_yields_one_per_event(self):
        agent = CoTPromptAgent()
        results = list(agent.run(iter(["a", "b"])))
        assert len(results) == 2


class TestCoTPromptAgentSettings:
    """AgentSettings 配置。"""

    def test_prompt_template_id(self):
        """自定义字段 prompt_template_id 可被访问。"""
        assert COT_PROMPT_AGENT_SETTINGS.prompt_template_id == "cot-v1"

    def test_capabilities(self):
        assert "cot" in COT_PROMPT_AGENT_SETTINGS.capabilities
        assert "prompt-template" in COT_PROMPT_AGENT_SETTINGS.capabilities

    def test_temperature_zero(self):
        assert COT_PROMPT_AGENT_SETTINGS.temperature == 0.0

    def test_topic_distinguishes_from_cot_demo(self):
        """topic 区别于 CoT Demo。"""
        assert COT_PROMPT_AGENT_SETTINGS.topic == "lesson2-cot-prompt-agent"


class TestCoTPromptAgentAttributes:
    """类属性。"""

    def test_class_attr_template(self):
        """CoTPromptAgent.template 是 CoT 模板。"""
        assert CoTPromptAgent.template is COT_REASONING_TEMPLATE

    def test_class_attr_agent_setting(self):
        """CoTPromptAgent.agent_setting 是 CoT Prompt Agent 的配置。"""
        assert CoTPromptAgent.agent_setting is COT_PROMPT_AGENT_SETTINGS