"""
Lesson 2: PromptTemplate — 把 prompt 抽象成可复用模板

本示例演示：
1. 如何用 dataclass/f-string 模式实现 PromptTemplate
2. 如何用 system + user 字段构造可复用的推理 prompt
3. 如何 format() 填入变量并产出最终 prompt
4. 如何与 tongagents 的 AgentSettings 配合（用 AgentSettings.topic 标注 prompt 类型）

运行方式：
    $ python prompt_template.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from string import Formatter
from typing import Any

from tongagents.agent import AgentSettings


# ============================================================
# 1. PromptTemplate：最简的 dataclass 实现
# ============================================================
#
# 思路：
#   - system / user 两段文本组成一个完整的 prompt
#   - {} 占位符变量用 str.format() 填入
#   - required_vars 自动从字符串里提取 {var_name}
#
# 为什么不直接用 f-string？
#   - Prompt 通常从文件 / 配置 / DB 加载，不是字面量
#   - 需要列出"必填变量"以提前校验
#   - 需要支持运行时覆盖（partial / bind）


@dataclass
class PromptTemplate:
    """一个最小可用的 Prompt 模板。

    Attributes:
        system: 系统提示，定义 LLM 的角色与行为边界
        user: 用户提示模板，{var_name} 占位符由 format() 填入
        required_vars: 占位符列表（自动从 user 中提取）
    """

    system: str
    user: str
    required_vars: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """从 user 字符串中提取 {var_name} 占位符。"""
        if not self.required_vars:
            formatter = Formatter()
            seen: set[str] = set()
            for _, field_name, _, _ in formatter.parse(self.user):
                if field_name is not None and field_name not in seen:
                    seen.add(field_name)
                    self.required_vars.append(field_name)

    def format(self, **kwargs: Any) -> dict[str, str]:
        """填入变量，返回完整的 {system, user} dict。

        Returns:
            dict[str, str]: {"system": ..., "user": ...}

        Raises:
            KeyError: 缺必填变量
        """
        missing = set(self.required_vars) - set(kwargs)
        if missing:
            raise KeyError(
                f"PromptTemplate 缺必填变量: {sorted(missing)} "
                f"(required: {self.required_vars})"
            )
        return {
            "system": self.system,
            "user": self.user.format(**kwargs),
        }

    def partial(self, **kwargs: Any) -> "PromptTemplate":
        """绑定部分变量，返回新模板（剩余变量仍待填）。

        只 substitute 已传入的 kwargs，其余占位符保持原样。
        """
        new_user = self.user
        for k, v in kwargs.items():
            new_user = new_user.replace("{" + k + "}", str(v)).replace(
                "{" + k + ":", "{" + k + ":"  # 不动带格式说明的
            )
        new_required = [
            v for v in self.required_vars if v not in kwargs
        ]
        return PromptTemplate(
            system=self.system,
            user=new_user,
            required_vars=new_required,
        )


# ============================================================
# 2. 几种典型 prompt 模板
# ============================================================

ZERO_SHOT_TEMPLATE = PromptTemplate(
    system="You are a helpful assistant. Answer concisely.",
    user="Question: {question}\nAnswer:",
)

FEW_SHOT_TEMPLATE = PromptTemplate(
    system="You are a helpful assistant. Answer by analogy to the examples.",
    user=(
        "Examples:\n"
        "  Q: 2+2?\n"
        "  A: 4\n"
        "  Q: 3+5?\n"
        "  A: 8\n"
        "\n"
        "Question: {question}\n"
        "Answer:"
    ),
)

COT_TEMPLATE = PromptTemplate(
    system="You are an expert who thinks step by step before answering.",
    user=(
        "Question: {question}\n"
        "\n"
        "Let's think step by step:\n"
        "Step 1: Identify what we know.\n"
        "Step 2: Identify what we need to find.\n"
        "Step 3: Apply relevant knowledge.\n"
        "Step 4: Calculate.\n"
        "Step 5: Verify.\n"
        "\n"
        "Final Answer:"
    ),
)

RAG_TEMPLATE = PromptTemplate(
    system=(
        "You are a knowledgeable assistant. Use the provided context to answer "
        "the question. If the context doesn't contain the answer, say 'I don't know'."
    ),
    user=(
        "Context:\n{context}\n"
        "\n"
        "Question: {question}\n"
        "\n"
        "Answer:"
    ),
)


# ============================================================
# 3. 与 AgentSettings 配合：把 prompt 模板注入 Agent 配置
# ============================================================
#
# AgentSettings 继承 Pydantic BaseModel，且 Config.extra="allow"。
# 所以我们可以往里塞自定义字段（如 prompt_template_id / template_name），
# 不影响 SDK 兼容性。

COT_AGENT_SETTINGS = AgentSettings(
    name="cot_prompt_agent",
    description="CoT reasoning agent with PromptTemplate",
    capabilities=["reasoning", "cot"],
    model="gpt-4",
    temperature=0.0,
    max_iterations=1,
    verbose=False,
    topic="lesson2-prompt-template",
    # 自定义字段（被 Config.extra="allow" 接受）
    prompt_template_id="cot-v1",
    template_name="cot_v1",
)


# ============================================================
# 4. 演示
# ============================================================

def demo_basic():
    """基本用法：填一个变量。"""
    print("=== demo_basic ===")
    rendered = ZERO_SHOT_TEMPLATE.format(question="What is 2+2?")
    print(rendered)
    print()


def demo_required_vars():
    """required_vars 自动提取。"""
    print("=== demo_required_vars ===")
    print("ZERO_SHOT_TEMPLATE.required_vars =", ZERO_SHOT_TEMPLATE.required_vars)
    print("COT_TEMPLATE.required_vars    =", COT_TEMPLATE.required_vars)
    print("RAG_TEMPLATE.required_vars    =", RAG_TEMPLATE.required_vars)
    print()


def demo_missing_var():
    """缺变量会抛 KeyError。"""
    print("=== demo_missing_var ===")
    try:
        ZERO_SHOT_TEMPLATE.format()
    except KeyError as e:
        print(f"KeyError: {e}")
    print()


def demo_partial():
    """partial 绑定部分变量。"""
    print("=== demo_partial ===")
    p = RAG_TEMPLATE.partial(context="[doc1] foo\n[doc2] bar")
    print("remaining required_vars =", p.required_vars)
    rendered = p.format(question="What is foo?")
    print(rendered)
    print()


def demo_with_agent_settings():
    """把 PromptTemplate 的元信息注入 AgentSettings。"""
    print("=== demo_with_agent_settings ===")
    print("name               =", COT_AGENT_SETTINGS.name)
    print("topic              =", COT_AGENT_SETTINGS.topic)
    print("prompt_template_id =", COT_AGENT_SETTINGS.prompt_template_id)
    print()


# ============================================================

def main() -> None:
    demo_basic()
    demo_required_vars()
    demo_missing_var()
    demo_partial()
    demo_with_agent_settings()


if __name__ == "__main__":
    main()