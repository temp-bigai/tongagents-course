"""llm — 模型调用 (TODO 1).

对 openai 包做最薄一层包装, 只暴露一个函数:
    llm_chat(messages, tools=None) -> message
agent.py 的循环只认这个接口 —— 模型怎么调、用哪家端点, 全部封在这里.
(自测 check_homework.py 会用一个 FakeLLM 顶替它, 所以函数必须可注入.)
"""
from __future__ import annotations

import os

from openai import OpenAI

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# 懒初始化: 不在 import 时构造客户端 —— 没配 Key 也能 import (自测就不需要 Key),
# 首次真正调用 llm_chat() 时才创建.
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        # api_key / base_url 自动读环境变量 OPENAI_API_KEY / OPENAI_BASE_URL
        _client = OpenAI()
    return _client


def llm_chat(messages: list, tools: list | None = None):
    """TODO(1): 调一次 chat.completions, 返回 message 对象.

    返回值的 message 有两个属性, agent.py 的循环全靠它们分流:
    - message.content:     str | None, 模型的文本回答 (不再要工具时才有)
    - message.tool_calls:  list | None, 模型想调的工具 (要工具时才有)

    实现提示 (对照课件 2.3 节 cell 15):
        resp = _get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,          # 注意: tools 为 None/空时不传这个参数,
            tool_choice="auto",   #       部分端点不接受空列表
        )
        return resp.choices[0].message
    """
    # TODO(1): 删除下面这行, 按上面提示实现
    raise NotImplementedError("Lesson 4 TODO(1): 实现 llm_chat")
