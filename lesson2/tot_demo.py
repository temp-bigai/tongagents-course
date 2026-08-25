"""
Lesson 2: Tree of Thoughts (ToT) — 树形搜索

ToT 是 CoT 的扩展：
    CoT:   question → step1 → step2 → ... → answer       (线性链)
    ToT:   question → [branch1, branch2, branch3]        (树形搜索)
                  →   [b1.1, b1.2]   [b2.1, b2.2]
                  →   评估 → 剪枝 → 扩展 → ...

核心三要素：
    1. 思维分解 (Thought Decomposition)：把问题拆成多步
    2. 思维生成 (Thought Generation)：每步生成多个候选
    3. 状态评估 (State Evaluation)：对每个候选打分

本示例演示：
1. 用 BFS 模拟 ToT 搜索
2. 评估函数 score_state()
3. 剪枝 + 选最优路径

运行方式：
    $ python tot_demo.py
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

from tongagents.agent import Agent, AgentSettings


# ============================================================
# 1. AgentSettings：配置 ToT Agent
# ============================================================

TOT_SETTINGS = AgentSettings(
    name="tot_agent",
    description="Tree of Thoughts — BFS/DFS over thought candidates with scoring",
    capabilities=["reasoning", "tot", "search"],
    model="gpt-4",
    temperature=0.8,
    max_iterations=4,
    verbose=False,
    topic="lesson2-tot",
    branch_factor=int(os.getenv("TOT_BRANCH_FACTOR", "3")),
    max_depth=int(os.getenv("TOT_MAX_DEPTH", "4")),
)


# ============================================================
# 2. ToT 的核心数据结构
# ============================================================

class ThoughtNode:
    """树中的一个节点。

    Attributes:
        state: 当前思维状态（字符串）
        score: 评估分数（越大越好）
        parent: 父节点
        children: 子节点列表
        depth: 所在深度
    """

    __slots__ = ("state", "score", "parent", "children", "depth")

    def __init__(
        self,
        state: str,
        score: float = 0.0,
        parent: "ThoughtNode | None" = None,
        depth: int = 0,
    ) -> None:
        self.state = state
        self.score = score
        self.parent = parent
        self.children: list[ThoughtNode] = []
        self.depth = depth

    def add_child(self, child: "ThoughtNode") -> None:
        self.children.append(child)

    def path_to_here(self) -> list[str]:
        """从根到当前节点的 state 列表。"""
        path: list[str] = []
        node: ThoughtNode | None = self
        while node is not None:
            path.append(node.state)
            node = node.parent
        return list(reversed(path))


# ============================================================
# 3. 评估函数：score_state()
# ============================================================

KEYWORDS_POSITIVE = ("possible", "solvable", "progress", "correct", "valid")
KEYWORDS_NEGATIVE = ("dead-end", "wrong", "invalid", "impossible", "contradiction")


def score_state(state: str) -> float:
    """对思维状态打分（越高越优）。

    真实运行中会让 LLM 打分；本示例用关键词启发式。
    """
    s = state.lower()
    pos = sum(1 for k in KEYWORDS_POSITIVE if k in s)
    neg = sum(1 for k in KEYWORDS_NEGATIVE if k in s)
    # 简单线性打分
    return 1.0 + 0.2 * pos - 0.5 * neg


# ============================================================
# 4. ToTAgent：BFS 搜索 + 评估 + 剪枝
# ============================================================

class ToTAgent(Agent):
    """Tree of Thoughts 搜索 Agent（BFS）。"""

    agent_setting = TOT_SETTINGS

    def __init__(
        self,
        branch_factor: int | None = None,
        max_depth: int | None = None,
    ) -> None:
        try:
            super().__init__(agent_setting=self.agent_setting)
        except TypeError:
            super().__init__()
        self.branch_factor = branch_factor or self.agent_setting.branch_factor
        self.max_depth = max_depth or self.agent_setting.max_depth

    def generate_thoughts(self, state: str) -> list[str]:
        """从当前 state 生成 branch_factor 个候选 thought。

        真实运行中会用 LLM.sample(state, n=self.branch_factor)。
        本示例用确定性 mock。
        """
        # mock：构造若干变体
        return [
            f"{state} -> approach_{i+1} (valid, progress on sub-step)"
            for i in range(self.branch_factor)
        ]

    def is_goal(self, state: str) -> bool:
        """终止条件。"""
        return "solved" in state.lower()

    def bfs(self, initial_state: str) -> dict[str, Any]:
        """BFS 搜索最优路径。"""
        root = ThoughtNode(state=initial_state, score=score_state(initial_state), depth=0)
        frontier: list[ThoughtNode] = [root]
        best_goal: ThoughtNode | None = None
        explored = 0

        while frontier:
            node = frontier.pop(0)
            explored += 1
            if self.is_goal(node.state):
                best_goal = node
                break
            if node.depth >= self.max_depth:
                continue

            # 生成候选
            for t_state in self.generate_thoughts(node.state):
                child = ThoughtNode(
                    state=t_state,
                    score=score_state(t_state),
                    parent=node,
                    depth=node.depth + 1,
                )
                node.add_child(child)
                frontier.append(child)

            # 剪枝：保留 frontier 中得分 top-k
            frontier.sort(key=lambda n: n.score, reverse=True)
            frontier = frontier[: self.branch_factor * self.max_depth]

        return {
            "explored": explored,
            "best_path": best_goal.path_to_here() if best_goal else root.path_to_here(),
            "best_score": best_goal.score if best_goal else root.score,
            "reached_goal": best_goal is not None,
        }

    # ---- Agent 接口 ----

    def step(self, event: Any) -> dict[str, Any]:
        if not isinstance(event, str):
            event = str(event)
        return self.bfs(event)

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
# 5. 演示
# ============================================================

def demo_score_state():
    """演示评估函数。"""
    print("=== demo_score_state ===")
    print(f"score('possible, progress, valid') = {score_state('possible, progress, valid')}")
    print(f"score('dead-end, invalid')        = {score_state('dead-end, invalid')}")
    print(f"score('progress')                 = {score_state('progress')}")
    print()


def demo_bfs():
    """完整 BFS 演示。"""
    print("=== demo_bfs ===")
    # mock 一个会在 step 2 触达 "solved" 的图：approach_2 触发 solved
    agent = ToTAgent(branch_factor=3, max_depth=3)
    # 这里覆盖 generate_thoughts 让它触达 goal
    def mock_generate(state):
        if state.endswith("approach_2"):
            return [f"{state} -> solved"]
        return [f"{state} -> approach_{i+1}" for i in range(3)]
    agent.generate_thoughts = mock_generate  # type: ignore

    result = agent.step("Start")
    print(f"explored     = {result['explored']}")
    print(f"reached_goal = {result['reached_goal']}")
    print(f"best_path    = {result['best_path']}")
    print()


def demo_settings_inspect():
    """检查 AgentSettings。"""
    print("=== demo_settings_inspect ===")
    print("name          =", TOT_SETTINGS.name)
    print("branch_factor =", TOT_SETTINGS.branch_factor)
    print("max_depth     =", TOT_SETTINGS.max_depth)
    print()


# ============================================================

def main() -> None:
    demo_settings_inspect()
    demo_score_state()
    demo_bfs()


if __name__ == "__main__":
    main()