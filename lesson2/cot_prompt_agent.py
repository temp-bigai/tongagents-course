"""
Lesson 2: CoT Prompt Agent（PPT Slide 43 完整实现）

把 Lesson 1 的 EchoAgent 升级为 CoTPromptAgent：
    EchoAgent:     input → output                       (1 step)
    CoTPromptAgent: input → CoT reasoning → final answer (N steps)

本示例对应课程 PPT 的 Slide 43：
    "CoT Prompt Agent = PromptTemplate + CoT Reasoning"

关键设计：
1. PromptTemplate 抽象 system + user 两段
2. AgentSettings 配置 CoT 推理参数
3. step() 输出结构化的 reasoning_steps + final_answer

运行方式：
    $ python cot_prompt_agent.py
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from typing import Any

from tongagents.agent import Agent, AgentSettings

from prompt_template import COT_TEMPLATE, PromptTemplate


# ============================================================
# 1. AgentSettings：CoT Prompt Agent 的运行时配置
# ============================================================

COT_PROMPT_AGENT_SETTINGS = AgentSettings(
    name="cot_prompt_agent",
    description="CoT Prompt Agent — uses PromptTemplate + step-by-step reasoning",
    capabilities=["reasoning", "cot", "prompt-template"],
    model="gpt-4",
    temperature=0.0,
    max_iterations=1,
    verbose=False,
    topic="lesson2-cot-prompt-agent",
    prompt_template_id="cot-v1",
)


# ============================================================
# 2. 扩展 PromptTemplate：CoT 专用的强类型模板
# ============================================================

COT_REASONING_TEMPLATE = PromptTemplate(
    system=(
        "You are an expert who thinks step by step before answering. "
        "Always show your reasoning, then give the final answer."
    ),
    user=(
        "Question: {question}\n"
        "\n"
        "Let's think step by step:\n"
        "Step 1: Identify what we know.\n"
        "Step 2: Identify what we need to find.\n"
        "Step 3: Apply relevant knowledge / formulas.\n"
        "Step 4: Calculate the result.\n"
        "Step 5: Verify by sanity check.\n"
        "\n"
        "Final Answer: <your answer here>\n"
    ),
)


# ============================================================
# 3. 响应解析：从 LLM 输出提取结构化字段
# ============================================================

STEP_PATTERN = re.compile(r"step\s+(\d+)\s*[:：]\s*(.+?)(?=\n\s*step\s+\d+|\n\s*final answer|\Z)", re.IGNORECASE | re.DOTALL)
FINAL_ANSWER_PATTERN = re.compile(r"final answer\s*[:：]\s*(.+?)\Z", re.IGNORECASE | re.DOTALL)


def parse_cot_response(response: str) -> dict[str, Any]:
    """解析 LLM 的 CoT 响应。

    Returns:
        dict: {
            "reasoning_steps": [step1_text, step2_text, ...],
            "final_answer": str | None,
            "raw_response": str,
        }
    """
    steps = [m.group(2).strip() for m in STEP_PATTERN.finditer(response)]
    match = FINAL_ANSWER_PATTERN.search(response)
    final = match.group(1).strip() if match else None
    return {
        "reasoning_steps": steps,
        "final_answer": final,
        "raw_response": response,
    }


# ============================================================
# 4. CoTPromptAgent：PPT Slide 43 的完整实现
# ============================================================

class CoTPromptAgent(Agent):
    """CoT Prompt Agent。

    与 Lesson 1 EchoAgent 的对比：
        EchoAgent.step("hello") → "Echo: hello"
        CoTPromptAgent.step("If 3 apples cost $6, how much do 10 apples cost?")
            → {
                "reasoning_steps": [...5 steps...],
                "final_answer": "$20",
                "raw_response": "Step 1: ...\n...\nFinal Answer: $20",
              }

    类属性:
        template: CoT 专用 PromptTemplate
        agent_setting: AgentSettings（带 prompt_template_id 标记）
    """

    agent_setting = COT_PROMPT_AGENT_SETTINGS
    template = COT_REASONING_TEMPLATE

    def __init__(self, llm: Any | None = None) -> None:
        # tongagents.Agent 的 __init__ 可能要求 agent_setting
        try:
            super().__init__(agent_setting=self.agent_setting)
        except TypeError:
            super().__init__()
        # 在真实场景中 llm 是 tongagents 的 LLM 客户端；本示例为 None
        self.llm = llm

    # ---- 核心方法 ----

    def step(self, event: Any) -> dict[str, Any]:
        """单步 CoT 推理。"""
        if not isinstance(event, str):
            event = str(event)
        prompt = self.template.format(question=event)
        # 真实运行：response = self.llm.generate(prompt)
        # mock：基于问题关键词构造确定性响应
        mock_response = self._mock_llm_response(event)
        return parse_cot_response(mock_response)

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

    # ---- 辅助方法 ----

    def _mock_llm_response(self, question: str) -> str:
        """Mock LLM 响应：基于关键词的确定性输出。"""
        q = question.lower()
        if "apples" in q:
            return (
                "Step 1: Identify what we know. 3 apples cost $6.\n"
                "Step 2: Identify what we need to find. The cost of 10 apples.\n"
                "Step 3: Apply relevant knowledge. Unit price = total / quantity = $6 / 3 = $2 per apple.\n"
                "Step 4: Calculate. 10 apples * $2/apple = $20.\n"
                "Step 5: Verify. $20 / 10 = $2 per apple, consistent with $6/3 = $2.\n"
                "\n"
                "Final Answer: $20"
            )
        if "train" in q or "speed" in q:
            return (
                "Step 1: Identify what we know. Speed = 60 mph, time = 2 hours.\n"
                "Step 2: Identify what we need to find. Distance traveled.\n"
                "Step 3: Apply relevant knowledge. distance = speed * time.\n"
                "Step 4: Calculate. 60 mph * 2 h = 120 miles.\n"
                "Step 5: Verify. 120 miles = 60 mph * 2 h, consistent.\n"
                "\n"
                "Final Answer: 120 miles"
            )
        return (
            "Step 1: Identify what we know. " + question + "\n"
            "Step 2: Identify what we need to find. A reasonable answer.\n"
            "Step 3: Apply relevant knowledge. General reasoning.\n"
            "Step 4: Calculate. Provide the best guess.\n"
            "Step 5: Verify. Sanity check.\n"
            "\n"
            "Final Answer: unknown"
        )


# ============================================================
# 5. 演示
# ============================================================

def demo_template_format():
    """演示 PromptTemplate.format() 产生完整 prompt。"""
    print("=== demo_template_format ===")
    rendered = CoTPromptAgent.template.format(
        question="A train travels 60 mph for 2 hours. How far?"
    )
    print("--- system ---")
    print(rendered["system"])
    print("--- user ---")
    print(rendered["user"])
    print()


def demo_single_reasoning():
    """演示完整 CoT 推理。"""
    print("=== demo_single_reasoning ===")
    agent = CoTPromptAgent()
    result = agent.step("If 3 apples cost $6, how much do 10 apples cost?")
    print(f"reasoning_steps ({len(result['reasoning_steps'])}):")
    for i, step in enumerate(result["reasoning_steps"], 1):
        print(f"  Step {i}: {step[:80]}{'...' if len(step) > 80 else ''}")
    print(f"final_answer = {result['final_answer']}")
    print()


def demo_stream():
    """演示流式推理。"""
    print("=== demo_stream ===")
    agent = CoTPromptAgent()
    questions = [
        "If 3 apples cost $6, how much do 10 apples cost?",
        "A train travels 60 mph for 2 hours. How far?",
    ]
    for result in agent.run(iter(questions)):
        print(f"  -> {result['final_answer']}")
    print()


def demo_settings_inspect():
    """演示 AgentSettings 的自定义字段。"""
    print("=== demo_settings_inspect ===")
    print(f"name                = {COT_PROMPT_AGENT_SETTINGS.name}")
    print(f"description         = {COT_PROMPT_AGENT_SETTINGS.description}")
    print(f"topic               = {COT_PROMPT_AGENT_SETTINGS.topic}")
    print(f"prompt_template_id  = {COT_PROMPT_AGENT_SETTINGS.prompt_template_id}")
    print()


# ============================================================

def main() -> None:
    demo_settings_inspect()
    demo_template_format()
    demo_single_reasoning()
    demo_stream()


if __name__ == "__main__":
    main()