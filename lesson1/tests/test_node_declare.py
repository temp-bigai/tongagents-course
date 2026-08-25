"""
Tests for @node_declare usage in lesson1.

Covers:
- Function decorator
- Class method decorator
- NodeBase + NodeConfig subclass
- Workflow.add_node + Workflow.run integration
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LESSON1_DIR = Path(__file__).resolve().parent.parent
if str(LESSON1_DIR) not in sys.path:
    sys.path.insert(0, str(LESSON1_DIR))


def test_node_declare_default_name_is_function_name():
    """@node_declare() without name uses the function name."""
    from node_declare_demo import add_one

    assert add_one.__node_config.name == "add_one"
    assert add_one.__node_config.edges == []


def test_node_declare_with_name_and_edges():
    from node_declare_demo import to_upper

    cfg = to_upper.__node_config
    assert cfg.name == "uppercase"
    assert cfg.edges == [("input", "output")]


def test_node_declare_on_class_method():
    """Decorating a class method attaches __node_config to the bound method."""
    from node_declare_demo import TextProcessor

    proc = TextProcessor()
    rev = proc.reverse_text
    assert rev.__node_config.name == "reverse"
    assert rev.__node_config.edges == [("input", "output")]


def test_node_base_subclass_with_pydantic_config():
    """NodeBase subclass + NodeConfig = strongly-typed node."""
    from node_declare_demo import GreetConfig, GreetNode

    config = GreetConfig(greeting="Hi", punctuation="~")
    node = GreetNode(config)
    assert node.greeting == "Hi"
    assert node.punctuation == "~"

    out = list(node.process(iter(["Alice", "Bob"]), context=None))
    assert out == ["Hi, Alice~", "Hi, Bob~"]


def test_simple_pipeline_upper_then_reverse():
    """Pipeline: upper -> reverse (节点函数直接串联)."""
    from node_declare_demo import demo_simple_pipeline

    out = demo_simple_pipeline()
    assert out == ["OLLEH", "STNEGAGNOT"]


def test_greet_pipeline():
    from node_declare_demo import demo_greet_pipeline

    out = demo_greet_pipeline()
    assert out == ["Hi, Alice~", "Hi, Bob~"]


def test_node_declare_demo_main_runs(capsys):
    from node_declare_demo import main

    main()
    captured = capsys.readouterr()
    assert "add_one 节点元数据" in captured.out
    assert "to_upper 节点元数据" in captured.out
    assert "TextProcessor.reverse_text" in captured.out
    assert "Pipeline: upper -> reverse" in captured.out
    assert "GreetNode.process 直接调用" in captured.out


@pytest.mark.parametrize(
    "input_text,expected",
    [
        ("hello", "olleh"),
        ("tongagents", "stnegagnot"),
        ("ABC", "CBA"),
        ("", ""),
    ],
)
def test_reverse_node_parametrized(input_text, expected):
    from node_declare_demo import TextProcessor

    proc = TextProcessor()
    out = list(proc.reverse_text(iter([input_text]), context=None))
    assert out == [expected]
