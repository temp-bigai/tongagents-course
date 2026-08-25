"""
Tests for lesson1.echo_agent — EchoAgent implementation.

These tests exercise the EchoAgent without requiring an LLM. The agent
is a deterministic state machine that returns "Echo: <input>".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make lesson1 importable when running `pytest` from the lesson1 directory.
LESSON1_DIR = Path(__file__).resolve().parent.parent
if str(LESSON1_DIR) not in sys.path:
    sys.path.insert(0, str(LESSON1_DIR))


def test_echo_settings_is_agent_settings():
    """ECHO_SETTINGS should be an AgentSettings instance."""
    from tongagents.agent import AgentSettings

    from echo_agent import ECHO_SETTINGS

    assert isinstance(ECHO_SETTINGS, AgentSettings)
    assert ECHO_SETTINGS.name == "echo_agent"
    assert "echo" in ECHO_SETTINGS.capabilities


def test_echo_agent_step_returns_prefixed_string():
    """EchoAgent.step(event) returns 'Echo: <event>'."""
    from echo_agent import ECHO_SETTINGS, EchoAgent

    agent = EchoAgent(agent_setting=ECHO_SETTINGS)
    assert agent.step("hello") == "Echo: hello"
    assert agent.step("你好") == "Echo: 你好"
    assert agent.step("") == "Echo: "


def test_echo_agent_run_yields_prefixed_strings():
    """EchoAgent.run(events) yields one prefixed string per input."""
    from echo_agent import ECHO_SETTINGS, EchoAgent

    agent = EchoAgent(agent_setting=ECHO_SETTINGS)
    inputs = iter(["foo", "bar", "baz"])
    outputs = list(agent.run(inputs))
    assert outputs == ["Echo: foo", "Echo: bar", "Echo: baz"]


def test_echo_agent_astep_returns_same_as_step():
    """Async single step mirrors sync step."""
    import asyncio

    from echo_agent import ECHO_SETTINGS, EchoAgent

    agent = EchoAgent(agent_setting=ECHO_SETTINGS)

    async def go():
        return await agent.astep("async-hello")

    result = asyncio.run(go())
    assert result == "Echo: async-hello"


def test_echo_agent_arun_yields_async():
    """Async run iterates an iterable and yields each result."""

    import asyncio

    from echo_agent import ECHO_SETTINGS, EchoAgent

    agent = EchoAgent(agent_setting=ECHO_SETTINGS)

    async def collect():
        return [r async for r in agent.arun(["a", "b", "c"])]

    out = asyncio.run(collect())
    assert out == ["Echo: a", "Echo: b", "Echo: c"]


def test_echo_agent_uses_class_level_settings_fallback():
    """If no agent_setting passed at construction, class-level ECHO_SETTINGS is used."""
    from echo_agent import ECHO_SETTINGS, EchoAgent

    agent = EchoAgent()
    # Class-level attribute is preserved
    assert agent.agent_setting is ECHO_SETTINGS
    assert agent.step("x") == "Echo: x"


def test_demo_workflow_pipelines_two_nodes():
    """demo_workflow composes echo_step -> shout, returning uppercased outputs."""
    from echo_agent import demo_workflow

    outputs = demo_workflow()
    # echo_step_node input ["hello", "tongagents", "lesson1"]
    # -> ["Echo: hello", "Echo: tongagents", "Echo: lesson1"]
    # shout_node -> ["ECHO: HELLO!", "ECHO: TONGAGENTS!", "ECHO: LESSON1!"]
    assert outputs == [
        "ECHO: HELLO!",
        "ECHO: TONGAGENTS!",
        "ECHO: LESSON1!",
    ]


def test_node_declare_attributes_present():
    """Decorated node carries __node_config with correct name and edges."""
    from echo_agent import echo_step_node

    assert hasattr(echo_step_node, "__node_config")
    cfg = echo_step_node.__node_config
    assert cfg.name == "echo_step"
    assert cfg.edges == [("input", "output")]
    assert cfg.with_context_when_called is False


def test_echo_node_typed_uses_config_prefix():
    """EchoNode (NodeBase + NodeConfig) uses config.prefix."""
    from echo_agent import EchoConfig, EchoNode

    node = EchoNode(EchoConfig(prefix="[Tong] "))
    outputs = list(node.process(iter(["a", "b"]), context=None))
    assert outputs == ["[Tong] a", "[Tong] b"]


def test_main_function_runs(capsys):
    """Smoke test: main() runs without error and prints expected sections."""
    from echo_agent import main

    main()
    captured = capsys.readouterr()
    assert "Lesson 1 — Echo Agent 演示" in captured.out
    assert "Agent.step() 同步调用" in captured.out
    assert "Agent.run() 流式处理" in captured.out
    assert "@node_declare 节点 pipeline" in captured.out
    assert "@node_declare 装饰器元数据" in captured.out


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("hi", "Echo: hi"),
        ("Hello, TongAgents!", "Echo: Hello, TongAgents!"),
        ("中文测试", "Echo: 中文测试"),
        ("123", "Echo: 123"),
    ],
)
def test_echo_agent_parametrized_inputs(input_text, expected):
    """Parametrized regression test for EchoAgent.step across input classes."""
    from echo_agent import EchoAgent

    agent = EchoAgent()
    assert agent.step(input_text) == expected
