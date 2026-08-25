"""
Lesson 1 辅助示例：AgentSettings 用法详解

本文件演示 AgentSettings 的各种配置方式。
- Pydantic 字段校验
- 默认值 vs 显式覆盖
- 通过 model_dump() 序列化为 dict
- 通过 extra="allow" 注入自定义字段

运行：
    $ python agent_settings_demo.py
"""

from __future__ import annotations

from tongagents.agent import AgentSettings


def demo_defaults():
    """使用所有默认值。"""
    s = AgentSettings()
    print("[1] 默认 AgentSettings:")
    print(f"    {s.model_dump()}")
    return s


def demo_explicit():
    """显式覆盖所有字段。"""
    s = AgentSettings(
        name="customer_service",
        description="Customer service agent for airport FAQ",
        capabilities=["faq", "translation", "escalation"],
        model="gpt-4o-mini",
        temperature=0.3,
        max_iterations=5,
        verbose=True,
        topic="airport_cs",
    )
    print("\n[2] 显式覆盖所有字段:")
    print(f"    name={s.name!r}, model={s.model!r}, temperature={s.temperature}")
    print(f"    capabilities={s.capabilities}")
    return s


def demo_extra_fields():
    """利用 extra='allow' 注入自定义字段。"""
    s = AgentSettings(
        name="custom_agent",
        description="Agent with extra fields",
        # 以下是 SDK 未定义但通过 extra='allow' 允许的字段
        custom_endpoint="https://llm.example.com/v1",
        region="cn-north-1",
        tags=["prod", "v2"],
    )
    print("\n[3] extra='allow' 注入自定义字段:")
    dump = s.model_dump()
    print(f"    standard fields: {list(AgentSettings.model_fields.keys())}")
    print(f"    extras: custom_endpoint={s.custom_endpoint!r}, region={s.region!r}")
    return s


def demo_serialize():
    """演示序列化与反序列化。"""
    s = AgentSettings(name="x", description="y", model="gpt-4")
    as_json = s.model_dump_json()
    print("\n[4] JSON 序列化:")
    print(f"    {as_json}")
    # 反序列化
    s2 = AgentSettings.model_validate_json(as_json)
    assert s == s2
    print("    ✓ 反序列化一致")
    return s


def main():
    demo_defaults()
    demo_explicit()
    demo_extra_fields()
    demo_serialize()
    print("\n✓ AgentSettings 演示完毕")


if __name__ == "__main__":
    main()
