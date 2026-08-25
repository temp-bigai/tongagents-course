"""
Lesson 2: Chain-of-Thought (CoT) Demo

把 Lesson 1 的 Echo Agent 升级为 CoT 推理 Agent。
Echo Agent 是"输入→输出"；CoT Agent 是"输入→多步推理→结论"。

本示例演示：
1. CoT 的核心思想：在 prompt 中显式要求"Let's think step by step"
2. 用 PromptTemplate 抽象 system + user 两段 prompt
3. 用 AgentSettings 配置推理参数（temperature=0 → 稳定输出）
4. step() 解析推理步骤；run() 串成完整推理链

运行方式：
    $ python cot_demo.py
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from typing import Any

from tongagents.agent import Agent, AgentSettings

from prompt_template import COT_TEMPLATE


# ============================================================
# 1. AgentSettings：配置 CoT 推理 Agent
# ============================================================

COT_AGENT_SETTINGS = AgentSettings(
    name="cot_agent",
    description="Chain-of-Thought reasoning agent — thinks step by step",
    capabilities=["reasoning", "cot", "math"],
    model="gpt-4",
    temperature=0.0,           # 推理任务用低温度，确保稳定
    max_iterations=1,
    verbose=False,
    topic="lesson2-cot",
)


# ============================================================
# 2. CoT 步骤解析：从 LLM 响应中提取结构化的推理步骤
# ============================================================

STEP_PATTERN = re.compile(r"step\s+(\d+)\s*[:：]\s*(.+?)(?=\n\s*step\s+\d+|\n\s*final answer|\Z)", re.IGNORECASE | re.DOTALL)
ANSWER_PATTERN = re.compile(r"final answer\s*[:：]\s*(.+?)\Z", re.IGNORECASE | re.DOTALL)


def parse_cot_response(response: str) -> dict[str, Any]:
    """从 LLM 响应中解析出 reasoning_steps 和 final_answer。

    期望响应形如：
        Step 1: Identify what we know. ...
        Step 2: Identify what we need to find. ...
        ...
        Final Answer: 20

    Returns:
        dict: {"reasoning_steps": [str, ...], "final_answer": str | None}
    """
    steps = [m.group(2).strip() for m in STEP_PATTERN.finditer(response)]
    answer_match = ANSWER_PATTERN.search(response)
    final = answer_match.group(1).strip() if answer_match else None
    return {"reasoning_steps": steps, "final_answer": final}


# ============================================================
# 3. CoTAgent：把 Echo Agent 升级为 CoT Agent
# ============================================================

class CoTAgent(Agent):
    """Chain-of-Thought 推理 Agent。

    与 EchoAgent 的对比：
        EchoAgent: input → output                  (1 step)
        CoTAgent:  input → step1 → step2 → ... → final   (N steps)

    CoT 的关键设计：
        1. PromptTemplate 显式要求"Let's think step by step"
        2. 输出结构化为 reasoning_steps + final_answer
        3. temperature=0 保证可复现
    """

    agent_setting = COT_AGENT_SETTINGS
    cot_template = COT_TEMPLATE

    def step(self, event: Any) -> dict[str, Any]:
        """单步推理：event 是问题字符串，返回 {reasoning_steps, final_answer}。"""
        if not isinstance(event, str):
            event = str(event)
        rendered = self.cot_template.format(question=event)
        # 在真实运行中这里会调用 self.llm.generate(rendered)
        # 本示例的 demo 用 mock 模拟 LLM 输出
        mock_response = self._mock_llm_response(event)
        return parse_cot_response(mock_response)

    def run(self, events: Iterator[Any]) -> Iterator[dict[str, Any]]:
        """流式处理事件，每条产生一个推理结果。"""
        for event in events:
            yield self.step(event)

    async def astep(self, event: Any) -> dict[str, Any]:
        """异步单步推理。"""
        return self.step(event)

    async def arun(self, events: AsyncIterator[Any] | Any) -> AsyncIterator[dict[str, Any]]:
        """异步流式处理。"""
        if hasattr(events, "__aiter__"):
            async for event in events:
                yield await self.astep(event)
        else:
            for event in events:
                yield await self.astep(event)

    def _mock_llm_response(self, question: str) -> str:
        """模拟 LLM 的 CoT 响应（真实运行时不调）。"""
        if "apples" in question.lower():
            return (
                "Step 1: Identify what we know. 3 apples cost $6.\n"
                "Step 2: Identify what we need to find. The cost of 10 apples.\n"
                "Step 3: Apply relevant knowledge. Unit price = $6 / 3 = $2 per apple.\n"
                "Step 4: Calculate. 10 apples * $2 = $20.\n"
                "Step 5: Verify. $20 = 10 * $2, and unit price $2 matches $6/3.\n"
                "\n"
                "Final Answer: $20"
            )
        if "train" in question.lower():
            return (
                "Step 1: Identify what we know. Speed = 60 mph, time = 2 hours.\n"
                "Step 2: Identify what we need to find. Distance.\n"
                "Step 3: Apply relevant knowledge. distance = speed * time.\n"
                "Step 4: Calculate. 60 * 2 = 120 miles.\n"
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
# 4. 演示
# ============================================================

def demo_single_question():
    """单问题推理。"""
    print("=== demo_single_question ===")
    agent = CoTAgent(agent_setting=COT_AGENT_SETTINGS)
    result = agent.step("If 3 apples cost $6, how much do 10 apples cost?")
    print("reasoning_steps:")
    for i, step in enumerate(result["reasoning_steps"], 1):
        print(f"  {i}. {step}")
    print(f"final_answer = {result['final_answer']}")
    print()


def demo_stream():
    """流式推理：多问题串行处理。"""
    print("=== demo_stream ===")
    agent = CoTAgent(agent_setting=COT_AGENT_SETTINGS)
    questions = [
        "If 3 apples cost $6, how much do 10 apples cost?",
        "A train travels 60 mph for 2 hours. How far?",
    ]
    for result in agent.run(iter(questions)):
        print(f"answer = {result['final_answer']}")
    print()


def demo_template_inspect():
    """检查 PromptTemplate 是否正确构造。"""
    print("=== demo_template_inspect ===")
    print("system    =", CoTAgent.cot_template.system)
    print("required  =", CoTAgent.cot_template.required_vars)
    rendered = CoTAgent.cot_template.format(question="What is 1+1?")
    print("rendered user =", rendered["user"][:80] + "...")
    print()


# ============================================================

def main() -> None:
    demo_template_inspect()
    demo_single_question()
    demo_stream()


if __name__ == "__main__":
    main()