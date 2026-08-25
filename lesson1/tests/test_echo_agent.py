from unittest.mock import Mock


def test_echo_agent_returns_input():
    from lesson1.echo_agent import EchoAgent
    agent = EchoAgent.__new__(EchoAgent)
    event = Mock(content="你好")
    result = agent.step(event)
    assert result.content == "你说：你好"
    assert result.role == "assistant"
