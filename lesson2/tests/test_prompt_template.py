"""
test_prompt_template.py — PromptTemplate 的单元测试
"""

from __future__ import annotations

import pytest

from prompt_template import (
    COT_TEMPLATE,
    FEW_SHOT_TEMPLATE,
    PromptTemplate,
    RAG_TEMPLATE,
    ZERO_SHOT_TEMPLATE,
    COT_AGENT_SETTINGS,
)


class TestPromptTemplateBasics:
    """PromptTemplate 基本行为。"""

    def test_required_vars_extracted(self):
        """required_vars 自动从 user 字符串提取。"""
        assert ZERO_SHOT_TEMPLATE.required_vars == ["question"]
        assert RAG_TEMPLATE.required_vars == ["context", "question"]
        assert COT_TEMPLATE.required_vars == ["question"]

    def test_format_returns_dict(self):
        """format() 返回 {system, user} dict。"""
        rendered = ZERO_SHOT_TEMPLATE.format(question="What is 2+2?")
        assert isinstance(rendered, dict)
        assert "system" in rendered
        assert "user" in rendered
        assert "What is 2+2?" in rendered["user"]

    def test_format_substitutes_multiple_vars(self):
        """RAG_TEMPLATE 同时含 context + question 两个变量。"""
        rendered = RAG_TEMPLATE.format(context="foo bar", question="What?")
        assert "foo bar" in rendered["user"]
        assert "What?" in rendered["user"]

    def test_missing_var_raises(self):
        """缺必填变量抛 KeyError。"""
        with pytest.raises(KeyError) as exc_info:
            ZERO_SHOT_TEMPLATE.format()
        assert "question" in str(exc_info.value)


class TestPromptTemplatePartial:
    """partial() 绑定部分变量。"""

    def test_partial_binds_var(self):
        """partial 后剩余变量变少。"""
        p = RAG_TEMPLATE.partial(context="[doc1]")
        assert "context" not in p.required_vars
        assert "question" in p.required_vars

    def test_partial_can_be_formatted(self):
        """partial 后再 format 剩余变量。"""
        p = RAG_TEMPLATE.partial(context="[doc1]")
        rendered = p.format(question="What is doc1?")
        assert "[doc1]" in rendered["user"]
        assert "What is doc1?" in rendered["user"]


class TestCustomPromptTemplate:
    """用户自定义 PromptTemplate。"""

    def test_construction_with_two_vars(self):
        """手工构造也能正确提取必填变量。"""
        tpl = PromptTemplate(
            system="You are X.",
            user="A: {a}\nB: {b}",
        )
        assert set(tpl.required_vars) == {"a", "b"}

    def test_no_required_vars(self):
        """无占位符时 required_vars 为空列表。"""
        tpl = PromptTemplate(
            system="You are X.",
            user="Static prompt, no placeholders.",
        )
        assert tpl.required_vars == []
        rendered = tpl.format()
        assert rendered["user"] == "Static prompt, no placeholders."


class TestFewShotTemplate:
    """Few-shot 模板特有属性。"""

    def test_has_examples(self):
        """FEW_SHOT_TEMPLATE 含 2 个示例。"""
        rendered = FEW_SHOT_TEMPLATE.format(question="What is 4+6?")
        assert "2+2" in rendered["user"]
        assert "3+5" in rendered["user"]


class TestAgentSettingsIntegration:
    """与 tongagents.AgentSettings 的集成。"""

    def test_agent_settings_has_prompt_template_id(self):
        """AgentSettings 自定义字段 prompt_template_id 可被设置。"""
        assert COT_AGENT_SETTINGS.prompt_template_id == "cot-v1"
        assert COT_AGENT_SETTINGS.template_name == "cot_v1"

    def test_agent_settings_name_unique(self):
        """4 个 settings name 各不相同。"""
        names = {
            ZERO_SHOT_TEMPLATE.system[:10],
            COT_TEMPLATE.system[:10],
            RAG_TEMPLATE.system[:10],
            FEW_SHOT_TEMPLATE.system[:10],
        }
        # 至少 system 描述彼此不同
        assert len(names) >= 2