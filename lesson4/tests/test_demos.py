import json

import pytest

from demo_cli import main
from tool_demo import calculate, dispatch_tool, get_weather


def test_weather_tool():
    assert get_weather("Shanghai")["temperature_c"] == 23


def test_calculator_restricts_syntax():
    assert calculate("(8 + 4) / 2")["result"] == 6
    with pytest.raises(ValueError):
        calculate("__import__('os').getcwd()")


def test_dispatcher_returns_json():
    result = json.loads(dispatch_tool("get_weather", '{"city":"Beijing"}'))
    assert result["found"] is True


def test_cli(capsys):
    assert main(["greet", "--name", "Agent"]) == 0
    assert capsys.readouterr().out.strip() == "Hello, Agent!"

