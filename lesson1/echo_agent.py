"""
Lesson 1: Echo Agent — 第一个 TongAgents Agent

本示例演示：
1. 如何 import tongagents SDK 的核心 API（Agent / AgentSettings）
2. 如何用 @node_declare 装饰器声明工作流节点
3. 如何用 AgentSettings 配置 Agent 行为
4. 如何直接调用 agent.step() 同步执行

运行方式：
    $ python echo_agent.py
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from tongagents.agent import Agent, AgentSettings
from tongagents.workflow.simple_workflow import (
    NodeBase,
    NodeConfig,
    node_declare,
)


# ============================================================
# 1. AgentSettings：定义 Agent 的元信息与运行参数
# ============================================================
#
# AgentSettings 是 Pydantic BaseModel，承载：
#   - name / description：Agent 的标识与描述
#   - capabilities：能力标签列表
#   - model / temperature / max_iterations：LLM 调用参数
#   - verbose：是否打印调试日志
#   - topic：业务主题
#
# 字段继承自 tongagents.agent.AgentSettings，可通过 Config.extra="allow"
# 注入自定义字段。Agent 会持有 agent_setting（无 s）作为运行时别名。

ECHO_SETTINGS = AgentSettings(
    name="echo_agent",
    description="Echo Agent — 把用户输入原样回显，前面加 'Echo: ' 前缀",
    capabilities=["echo", "text"],
    model="gpt-4",
    temperature=0.0,
    max_iterations=1,
    verbose=True,
    topic="lesson1",
)


# ============================================================
# 2. Agent 子类：实现核心 run / step / arun / astep 四个方法
# ============================================================
#
# tongagents.agent.Agent 是抽象基类，子类必须实现：
#   - run(events: Iterator) -> Iterator        # 流式同步
#   - step(event) -> Any                       # 单步同步
#   - arun(events: AsyncIterator) -> AsyncIterator  # 流式异步
#   - astep(event) -> Any                      # 单步异步

class EchoAgent(Agent):
    """第一个 Agent：把用户输入原样回显，前面加 'Echo: ' 前缀。"""

    agent_setting = ECHO_SETTINGS

    def step(self, event: Any) -> str:
        """处理单条事件，返回字符串回复。"""
        return f"Echo: {event}"

    def run(self, events: Iterator[Any]) -> Iterator[str]:
        """流式处理事件，每条产生一个回复。"""
        for event in events:
            yield self.step(event)

    async def astep(self, event: Any) -> str:
        """异步单步处理。"""
        return self.step(event)

    async def arun(self, events: AsyncIterator[Any] | Any) -> AsyncIterator[str]:
        """异步流式处理。"""
        # 支持传入 async iterator 或可调用对象
        if hasattr(events, "__aiter__"):
            async for event in events:
                yield await self.astep(event)
        else:
            for event in events:
                yield await self.astep(event)


# ============================================================
# 3. @node_declare：把普通函数声明为工作流节点
# ============================================================
#
# node_declare 是 tongagents.workflow 的核心装饰器：
#   - name：节点名（默认取函数名）
#   - edges：从本节点出发的边，列表 of (from_port, to_port)
#   - with_context_when_called：调用时是否传入 context
#   - input_process_mode：DEFAULT / ACCUMULATE / LATEST
#   - run_mode：SERIAL（默认）/ THREAD（并行）
#
# 装饰后的函数会带上 __node_config 属性（NodeConfig 实例）。

@node_declare(
    name="echo_step",
    edges=[("input", "output")],
    with_context_when_called=False,
)
def echo_step_node(events, context=None):
    """节点函数：yield 形式的流式处理。"""
    for event in events:
        yield f"Echo: {event}"


@node_declare(
    name="shout",
    edges=[("input", "output")],
)
def shout_node(events, context=None):
    """变体节点：把输入转大写并加感叹号。"""
    for event in events:
        yield f"{str(event).upper()}!"


# ============================================================
# 4. NodeBase 子类：基于 Pydantic 配置的强类型节点
# ============================================================
#
# 当节点的入参需要结构化校验时，可以继承 NodeBase + NodeConfig。
# 这是 workflow JSON 模式下注册节点的标准做法。

class EchoConfig(NodeConfig):
    """基于 NodeConfig 的强类型配置。

    NodeConfig 必须的字段：name / type / with_context_when_called。
    继承时需要在子类默认值中提供，否则调用方必须显式传入。
    """

    prefix: str = "Echo: "
    # 覆盖父类必填字段
    name: str = "echo_typed"
    type: str = "echo_typed"
    with_context_when_called: bool = False


class EchoNode(NodeBase):
    """基于 Pydantic 配置的 Echo 节点。"""

    def __init__(self, config: EchoConfig):
        super().__init__(config)
        self.prefix = config.prefix

    @node_declare(name="echo_typed")
    def process(self, events, context=None):
        for event in events:
            yield self.prefix + str(event)


# ============================================================
# 5. 演示：节点函数的直接调用（最直观的 pipeline 演示）
# ============================================================
#
# lesson1 不演示完整 Workflow 编排（DDS / NodeConfig / JSON workflow 等
# 概念在 lesson2 中详细讲解）。这里用 Python 自身的 generator 链接来
# 展示 @node_declare 的本质——就是一个 yield 流式函数。
#
# 完整的 Workflow 编排见 lesson2。

def demo_workflow():
    """手动把两个节点串成 pipeline：echo_step -> shout。"""
    # 阶段 1：echo_step 处理
    echo_outputs = list(echo_step_node(iter(["hello", "tongagents", "lesson1"]), context=None))
    # 阶段 2：shout 把 echo 的输出再处理一次
    final_outputs = list(shout_node(iter(echo_outputs), context=None))
    return final_outputs


# ============================================================
# CLI 入口
# ============================================================

def main():
    """主函数：演示 Echo Agent 的三种调用方式。"""
    print("=" * 60)
    print("Lesson 1 — Echo Agent 演示")
    print("=" * 60)

    # 方式 1：直接用 AgentSettings + Agent（推荐入门方式）
    print("\n[1] Agent.step() 同步调用：")
    agent = EchoAgent(agent_setting=ECHO_SETTINGS)
    result = agent.step("Hello, TongAgents!")
    print(f"    agent.step('Hello, TongAgents!') -> '{result}'")

    # 方式 2：Agent 流式处理
    print("\n[2] Agent.run() 流式处理：")
    inputs = ["foo", "bar", "baz"]
    for i, out in enumerate(agent.run(iter(inputs))):
        print(f"    out[{i}] = '{out}'")

    # 方式 3：节点 pipeline 演示
    print("\n[3] @node_declare 节点 pipeline：")
    outputs = demo_workflow()
    for i, out in enumerate(outputs):
        print(f"    outputs[{i}] = '{out}'")

    # 方式 4：验证 @node_declare 装饰器
    print("\n[4] @node_declare 装饰器元数据：")
    print(f"    echo_step_node.__node_config.name = '{echo_step_node.__node_config.name}'")
    print(f"    echo_step_node.__node_config.edges = {echo_step_node.__node_config.edges}")
    print(f"    shout_node.__node_config.name = '{shout_node.__node_config.name}'")

    print("\n" + "=" * 60)
    print("✓ Lesson 1 Echo Agent 演示完毕。下一步：lesson2 Workflow 进阶。")
    print("=" * 60)


if __name__ == "__main__":
    main()
