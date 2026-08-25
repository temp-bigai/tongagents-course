from unittest.mock import AsyncMock


def test_cot_agent_delegates_to_llm():
    from lesson2.cot_prompt_agent import CoTPromptAgent
    llm = Mock()
    llm.complete = AsyncMock(return_value="42")
    agent = CoTPromptAgent(llm)
    import asyncio
    assert asyncio.run(agent.run("1+1")) == "42"
