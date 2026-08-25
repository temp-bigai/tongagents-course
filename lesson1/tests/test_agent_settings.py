"""
Tests for AgentSettings (tongagents.agent.AgentSettings).

These tests verify:
- Default values
- Explicit field assignment
- extra='allow' (custom fields via Pydantic Config.extra)
- JSON serialization round-trip
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

LESSON1_DIR = Path(__file__).resolve().parent.parent
if str(LESSON1_DIR) not in sys.path:
    sys.path.insert(0, str(LESSON1_DIR))


def test_agent_settings_defaults():
    from tongagents.agent import AgentSettings

    s = AgentSettings()
    assert s.name == "default"
    assert s.description == ""
    assert s.capabilities == []
    assert s.model == "gpt-4"
    assert s.temperature == 0.7
    assert s.max_iterations == 10
    assert s.verbose is False
    assert s.topic == "general"


def test_agent_settings_explicit_override():
    from tongagents.agent import AgentSettings

    s = AgentSettings(
        name="x",
        description="y",
        capabilities=["a", "b"],
        model="gpt-4o",
        temperature=0.0,
        max_iterations=3,
        verbose=True,
        topic="t",
    )
    assert s.name == "x"
    assert s.capabilities == ["a", "b"]
    assert s.model == "gpt-4o"
    assert s.temperature == 0.0
    assert s.max_iterations == 3
    assert s.verbose is True
    assert s.topic == "t"


def test_agent_settings_extra_fields_allowed():
    """AgentSettings.Config.extra == 'allow' → custom fields accepted."""
    from tongagents.agent import AgentSettings

    s = AgentSettings(
        name="custom",
        custom_endpoint="https://llm.example.com",
        region="cn-north-1",
        tags=["prod"],
    )
    dump = s.model_dump()
    assert dump["custom_endpoint"] == "https://llm.example.com"
    assert dump["region"] == "cn-north-1"
    assert dump["tags"] == ["prod"]


def test_agent_settings_invalid_temperature_rejected():
    """Pydantic should reject invalid types (e.g. str for temperature)."""
    from tongagents.agent import AgentSettings

    with pytest.raises(ValidationError):
        AgentSettings(temperature="not-a-float")  # type: ignore[arg-type]


def test_agent_settings_json_roundtrip():
    from tongagents.agent import AgentSettings

    original = AgentSettings(name="rt", description="round-trip", model="gpt-4o-mini")
    as_json = original.model_dump_json()
    restored = AgentSettings.model_validate_json(as_json)
    assert restored == original


def test_agent_settings_model_dump_keys():
    """model_dump() should contain all defined fields."""
    from tongagents.agent import AgentSettings

    s = AgentSettings()
    keys = set(s.model_dump().keys())
    expected_keys = {
        "name", "description", "capabilities", "model",
        "temperature", "max_iterations", "verbose", "topic",
    }
    assert expected_keys.issubset(keys)


def test_agent_settings_demo_runs(capsys):
    """Smoke test for the standalone demo script."""
    from agent_settings_demo import main

    main()
    captured = capsys.readouterr()
    assert "默认 AgentSettings" in captured.out
    assert "显式覆盖所有字段" in captured.out
    assert "extra='allow' 注入自定义字段" in captured.out
    assert "JSON 序列化" in captured.out
