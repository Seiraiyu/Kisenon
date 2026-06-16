import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from agent_sandbox.providers.openai_provider import OpenAIProvider


def _function(name: str, arguments: dict):
    return SimpleNamespace(name=name, arguments=json.dumps(arguments))


def _tool_call(id_: str, name: str, arguments: dict):
    return SimpleNamespace(id=id_, type="function", function=_function(name, arguments))


def _message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls or [])


def _completion(message, finish_reason: str = "stop"):
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], id="cmpl_x", model="gpt-5.1")


def test_run_turn_parses_text_content_as_final_answer():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion(
        _message(content="3,142 users."),
        finish_reason="stop",
    )
    p = OpenAIProvider(model="gpt-5.1", client=client)
    out = p.run_turn(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert out.text == "3,142 users."
    assert out.tool_calls == []


def test_run_turn_parses_tool_calls():
    client = MagicMock()
    client.chat.completions.create.return_value = _completion(
        _message(tool_calls=[_tool_call("call_1", "run_sql", {"sql": "SELECT 1"})]),
        finish_reason="tool_calls",
    )
    p = OpenAIProvider(model="gpt-5.1", client=client)
    out = p.run_turn(
        messages=[{"role": "user", "content": "go"}],
        tools=[{"type": "function", "function": {"name": "run_sql",
                                                  "description": "...",
                                                  "parameters": {}}}],
    )
    assert out.text is None
    assert len(out.tool_calls) == 1
    assert out.tool_calls[0].id == "call_1"
    assert out.tool_calls[0].name == "run_sql"
    assert out.tool_calls[0].arguments == {"sql": "SELECT 1"}


def test_encode_user_message_returns_simple_role_content():
    p = OpenAIProvider(model="gpt-5.1", client=MagicMock())
    assert p.encode_user_message("hi") == {"role": "user", "content": "hi"}


def test_encode_tool_result_returns_tool_role_message():
    p = OpenAIProvider(model="gpt-5.1", client=MagicMock())
    assert p.encode_tool_result("call_42", "ok") == {
        "role": "tool",
        "tool_call_id": "call_42",
        "content": "ok",
    }
