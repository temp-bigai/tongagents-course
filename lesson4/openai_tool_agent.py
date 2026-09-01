"""Optional OpenAI-compatible tool-calling loop for the Lesson 4 notebook."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI

from tool_demo import TOOLS, dispatch_tool


def configured_client() -> tuple[OpenAI, str]:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    if not api_key or api_key == "your-api-key" or not model:
        raise RuntimeError("Set OPENAI_API_KEY and OPENAI_MODEL in lesson4/.env first")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    return OpenAI(api_key=api_key, base_url=base_url), model


def run_tool_agent(question: str) -> str:
    """Run one model turn, execute requested tools, then ask for a final answer."""
    client, model = configured_client()
    messages: list[dict] = [
        {
            "role": "system",
            "content": "Use the provided tools when useful. Keep the final answer concise.",
        },
        {"role": "user", "content": question},
    ]
    first = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
    assistant = first.choices[0].message
    messages.append(assistant.model_dump(exclude_none=True))

    for call in assistant.tool_calls or []:
        result = dispatch_tool(call.function.name, call.function.arguments)
        messages.append(
            {"role": "tool", "tool_call_id": call.id, "content": result}
        )

    if not assistant.tool_calls:
        return assistant.content or ""
    final = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
    return final.choices[0].message.content or ""

