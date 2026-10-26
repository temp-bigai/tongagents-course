"""registry — 工具注册表 (已给, 不需要修改).

对应 OpenAI function calling 的两端:
- TOOLS:          发给模型的 schema 列表 (tools= 参数), 告诉模型"有哪些工具、怎么传参"
- TOOL_REGISTRY:  名字 -> 函数 的派发表, 模型决定调用后按名字找到实现去执行

tools.py 里每写好一个工具就 register(...) 一次; agent.py 的循环里
用 TOOLS 发请求、用 call_tool() 执行 —— 注册表就是两者的连接点.
"""
from __future__ import annotations

import json
from typing import Callable

# 发给模型的 schema 列表: [{"type": "function", "function": {...}}, ...]
TOOLS: list[dict] = []

# 名字 -> 实现 函数 的派发表
TOOL_REGISTRY: dict[str, Callable] = {}


def register(name: str, description: str, parameters: dict, fn: Callable) -> None:
    """注册一个工具: 记录 schema (给模型看) 并登记实现 (给自己执行)."""
    if name in TOOL_REGISTRY:
        raise ValueError(f"工具重复注册: {name}")
    TOOLS.append(
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
    )
    TOOL_REGISTRY[name] = fn


def call_tool(name: str, arguments) -> str:
    """执行一个工具调用, 统一返回字符串.

    模型回传的 arguments 是 JSON 字符串 (也可能已被解析成 dict), 这里:
    解析参数 -> 按名字派发 -> str() 结果.
    任何失败 (未知工具 / JSON 解析失败 / 参数不匹配 / 工具内部异常) 都不抛异常,
    而是返回 "error: ..." 字符串 —— 错误信息也要回传给模型, 它会自己想办法.
    """
    if name not in TOOL_REGISTRY:
        return f"error: 未知工具 '{name}'"

    if isinstance(arguments, str):
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError as e:
            return f"error: 参数不是合法 JSON: {e}"
    else:
        args = dict(arguments or {})

    try:
        return str(TOOL_REGISTRY[name](**args))
    except TypeError as e:
        return f"error: 参数不匹配: {e}"
    except Exception as e:  # noqa: BLE001 —— 工具异常也作为结果回传
        return f"error: {type(e).__name__}: {e}"
