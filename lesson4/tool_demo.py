"""Small, deterministic tools used by the Lesson 4 notebook."""

from __future__ import annotations

import ast
import json
import operator
from collections.abc import Callable
from typing import Any


WEATHER = {
    "beijing": {"temperature_c": 18, "condition": "sunny"},
    "shanghai": {"temperature_c": 23, "condition": "cloudy"},
    "shenzhen": {"temperature_c": 27, "condition": "rain"},
}


def get_weather(city: str) -> dict[str, Any]:
    """Return deterministic sample weather data for a city."""
    normalized = city.strip().lower()
    result = WEATHER.get(normalized)
    if result is None:
        return {"city": city, "found": False, "message": "No sample data"}
    return {"city": city, "found": True, **result}


_BINARY_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_expression(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_expression(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        return _BINARY_OPS[type(node.op)](
            _eval_expression(node.left), _eval_expression(node.right)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_expression(node.operand))
    raise ValueError("Only numbers and +, -, *, / are allowed")


def calculate(expression: str) -> dict[str, float | str]:
    """Evaluate a deliberately small arithmetic language without using eval."""
    if len(expression) > 100:
        raise ValueError("Expression is too long")
    tree = ast.parse(expression, mode="eval")
    return {"expression": expression, "result": _eval_expression(tree)}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get sample weather for Beijing, Shanghai, or Shenzhen.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name in English"}
                },
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Calculate an arithmetic expression using +, -, *, and /.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
                "additionalProperties": False,
            },
        },
    },
]

_IMPLEMENTATIONS: dict[str, Callable[..., Any]] = {
    "get_weather": get_weather,
    "calculate": calculate,
}


def dispatch_tool(name: str, arguments: str | dict[str, Any]) -> str:
    """Validate the tool name, decode arguments, and return JSON text."""
    if name not in _IMPLEMENTATIONS:
        raise ValueError(f"Tool is not allowed: {name}")
    parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
    if not isinstance(parsed, dict):
        raise TypeError("Tool arguments must be a JSON object")
    return json.dumps(_IMPLEMENTATIONS[name](**parsed), ensure_ascii=False)

