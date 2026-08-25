"""
Lesson 2: Self-Consistency — 多路径 CoT 采样 + 投票

Self-Consistency 思想：
    对同一问题，独立采样 N 次 CoT 推理，统计最终答案的众数。
    多次"思考路径"汇总，比单一 greedy decoding 更鲁棒。

本示例演示：
1. 如何在 CoTAgent 基础上加多次采样
2. 用 collections.Counter 做投票
3. 用 AgentSettings 配置采样参数 n_samples

运行方式：
    $ python cot_self_consistency.py
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import AsyncIterator, Iterator
from typing import Any

from tongagents.agent import Agent, AgentSettings

from cot_demo import CoTAgent, parse_cot_response
from prompt_template import COT_TEMPLATE


# ============================================================
# 1. AgentSettings：配置 Self-Consistency Agent
# ============================================================

SELF_CONSISTENCY_SETTINGS = AgentSettings(
    name="self_consistency_agent",
    description="Self-Consistency — sample N CoT paths, take majority vote",
    capabilities=["reasoning", "cot", "self-consistency", "voting"],
    model="gpt-4",
    # Self-Consistency 通常需要 temperature > 0 来采样多样性
    temperature=0.7,
    max_iterations=int(os.getenv("SELF_CONSISTENCY_N_SAMPLES", "5")),
    verbose=False,
    topic="lesson2-self-consistency",
    n_samples=int(os.getenv("SELF_CONSISTENCY_N_SAMPLES", "5")),
)


# ============================================================
# 2. SelfConsistencyAgent：在 CoTAgent 基础上加 N 次采样 + 投票
# ============================================================

class SelfConsistencyAgent(Agent):
    """多次 CoT 采样 + 投票选最优。

    算法流程：
        for i in 1..N:
            response = sample_cot(question)        # 温度 T > 0 采样
            answer = parse_cot(response).final_answer
        return majority_vote([answer_1, ..., answer_N])
    """

    agent_setting = SELF_CONSISTENCY_SETTINGS
    cot_template = COT_TEMPLATE

    def __init__(
        self,
        n_samples: int | None = None,
        cot_agent: CoTAgent | None = None,
    ) -> None:
        # tongagents.Agent 通常需要 agent_setting 参数（这里我们用类属性已经设置）
        # 但父类 __init__ 会检查，下面兼容两种调用方式
        try:
            super().__init__(agent_setting=self.agent_setting)
        except TypeError:
            super().__init__()
        self.n_samples = n_samples or self.agent_setting.n_samples
        self.cot_agent = cot_agent or CoTAgent(agent_setting=CoTAgent.agent_setting)

    # ---- 投票工具 ----

    def vote(self, answers: list[str]) -> tuple[str, int]:
        """对 N 个最终答案做投票，返回 (众数, 票数)。

        平票时取字典序最小的（deterministic tiebreak）。
        """
        if not answers:
            raise ValueError("vote(): answers is empty")
        counter = Counter(answers)
        max_count = max(counter.values())
        # 平票：取字典序最小的
        winners = sorted(
            [a for a, c in counter.items() if c == max_count]
        )
        return winners[0], max_count

    # ---- 单步 ----

    def step(self, event: Any) -> dict[str, Any]:
        """单步推理：多次采样 CoT，投票。"""
        if not isinstance(event, str):
            event = str(event)

        # 1) N 次采样
        answers: list[str] = []
        all_steps: list[list[str]] = []
        for i in range(self.n_samples):
            # 在真实运行中：每次 sample 时给 LLM 一个不同的 temperature/seed
            parsed = self.cot_agent.step(event)
            final = parsed.get("final_answer") or "<empty>"
            answers.append(final)
            all_steps.append(parsed.get("reasoning_steps", []))

        # 2) 投票
        winner, count = self.vote(answers)

        return {
            "question": event,
            "samples": answers,
            "reasoning_steps_per_sample": all_steps,
            "winner": winner,
            "vote_count": count,
            "vote_ratio": round(count / self.n_samples, 4),
        }

    # ---- 流式 ----

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
# 3. 演示
# ============================================================

def demo_vote_only():
    """演示投票工具（不跑 Agent）。"""
    print("=== demo_vote_only ===")
    agent = SelfConsistencyAgent(n_samples=5)
    answers = ["$20", "$20", "$20", "$18", "$22"]
    winner, count = agent.vote(answers)
    print(f"answers = {answers}")
    print(f"winner  = {winner} (votes = {count}/{len(answers)})")
    print()


def demo_self_consistency():
    """完整演示：5 次 CoT 采样 → 投票。"""
    print("=== demo_self_consistency ===")
    agent = SelfConsistencyAgent(n_samples=5)
    result = agent.step("If 3 apples cost $6, how much do 10 apples cost?")
    print(f"question   = {result['question']}")
    print(f"samples    = {result['samples']}")
    print(f"winner     = {result['winner']}")
    print(f"vote_count = {result['vote_count']}/{len(result['samples'])}")
    print(f"vote_ratio = {result['vote_ratio']}")
    print()


def demo_settings_inspect():
    """检查 AgentSettings 是否带 n_samples。"""
    print("=== demo_settings_inspect ===")
    print("name             =", SELF_CONSISTENCY_SETTINGS.name)
    print("temperature      =", SELF_CONSISTENCY_SETTINGS.temperature)
    print("max_iterations   =", SELF_CONSISTENCY_SETTINGS.max_iterations)
    print("n_samples (extra)=", SELF_CONSISTENCY_SETTINGS.n_samples)
    print()


# ============================================================

def main() -> None:
    demo_settings_inspect()
    demo_vote_only()
    demo_self_consistency()


if __name__ == "__main__":
    main()