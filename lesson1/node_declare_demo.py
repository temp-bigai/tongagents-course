"""
Lesson 1 辅助示例：@node_declare 装饰器用法详解

本文件演示 @node_declare 的多种使用方式：
- 函数装饰器（最简形式）
- 带 edges 的节点（连边声明）
- 修饰类方法
- 自定义 NodeConfig（强类型入参）

运行：
    $ python node_declare_demo.py
"""

from __future__ import annotations

from tongagents.workflow.simple_workflow import (
    NodeBase,
    NodeConfig,
    node_declare,
)


# ============================================================
# 1. 最简形式：默认 name 取函数名，无 edges
# ============================================================

@node_declare()
def add_one(events, context=None):
    """每个事件 +1。"""
    for x in events:
        yield x + 1


# ============================================================
# 2. 指定 name + edges
# ============================================================

@node_declare(name="uppercase", edges=[("input", "output")])
def to_upper(events, context=None):
    """把每个事件转大写。"""
    for text in events:
        yield text.upper()


# ============================================================
# 3. 修饰类方法
# ============================================================

class TextProcessor:
    """包含两个节点的处理器。"""

    @node_declare(name="reverse", edges=[("input", "output")])
    def reverse_text(self, events, context=None):
        for text in events:
            yield text[::-1]

    @node_declare(name="length", edges=[("input", "output")])
    def text_length(self, events, context=None):
        for text in events:
            yield len(text)


# ============================================================
# 4. 强类型节点：NodeConfig + NodeBase
# ============================================================

class GreetConfig(NodeConfig):
    """问候语节点的配置。

    NodeConfig 必须的字段：name / type / with_context_when_called。
    继承时需要在子类默认值中提供。
    """

    greeting: str = "Hello"
    punctuation: str = "!"
    name: str = "greet"
    type: str = "greet"
    with_context_when_called: bool = False


class GreetNode(NodeBase):
    """基于配置的问候节点。"""

    def __init__(self, config: GreetConfig):
        super().__init__(config)
        self.greeting = config.greeting
        self.punctuation = config.punctuation

    @node_declare(name="greet")
    def process(self, events, context=None):
        for name in events:
            yield f"{self.greeting}, {name}{self.punctuation}"


# ============================================================
# 5. 节点函数直接串联（最直观的 pipeline 演示）
# ============================================================
#
# lesson1 不演示完整 Workflow 编排（DDS / NodeConfig / JSON workflow 等
# 概念在 lesson2 中详细讲解）。这里用 Python 自身的 generator 链式
# 串联演示——把上一个节点的输出喂给下一个节点。

def demo_simple_pipeline():
    """upper -> reverse：把节点函数直接串联。"""
    inputs = ["hello", "tongagents"]
    upper_outputs = list(to_upper(iter(inputs), context=None))
    rev_outputs = list(TextProcessor().reverse_text(iter(upper_outputs), context=None))
    return rev_outputs


def demo_greet_pipeline():
    """使用 GreetNode.process 一次性处理多个名字。"""
    greet_node = GreetNode(GreetConfig(greeting="Hi", punctuation="~"))
    inputs = ["Alice", "Bob"]
    outputs = list(greet_node.process(iter(inputs), context=None))
    return outputs


def main():
    print("=" * 60)
    print("Lesson 1 — @node_declare 装饰器演示")
    print("=" * 60)

    # 1. 基本属性
    print("\n[1] add_one 节点元数据:")
    print(f"    name: {add_one.__node_config.name!r}")
    print(f"    type: {add_one.__node_config.type!r}")
    print(f"    edges: {add_one.__node_config.edges}")

    # 2. 带 edges
    print("\n[2] to_upper 节点元数据:")
    print(f"    name: {to_upper.__node_config.name!r}")
    print(f"    edges: {to_upper.__node_config.edges}")

    # 3. 修饰类方法
    print("\n[3] TextProcessor.reverse_text 节点元数据:")
    proc = TextProcessor()
    rev_config = proc.reverse_text.__node_config
    print(f"    name: {rev_config.name!r}, edges: {rev_config.edges}")

    # 4. Pipeline 演示：节点函数直接串联
    print("\n[4] Pipeline: upper -> reverse (节点函数直接串联):")
    for out in demo_simple_pipeline():
        print(f"    {out!r}")

    # 5. 强类型节点
    print("\n[5] GreetNode.process 直接调用 (GreetConfig + GreetNode):")
    for out in demo_greet_pipeline():
        print(f"    {out!r}")

    print("\n" + "=" * 60)
    print("✓ @node_declare 演示完毕")
    print("=" * 60)


if __name__ == "__main__":
    main()
