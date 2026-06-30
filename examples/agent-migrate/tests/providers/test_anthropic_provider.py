from types import SimpleNamespace
from unittest.mock import MagicMock

from agent_migrate.providers.anthropic_provider import AnthropicProvider


def _block_text(text: str):
    return SimpleNamespace(type="text", text=text)


def _block_tool_use(id_: str, name: str, input_: dict):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def _message(content, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        content=content, stop_reason=stop_reason,
        model="claude-sonnet-4-6", id="msg_x", role="assistant",
    )


def test_run_turn_parses_text_block_as_final_answer():
    client = MagicMock()
    client.messages.create.return_value = _message([_block_text("3,142 users.")])
    p = AnthropicProvider(model="claude-sonnet-4-6", client=client)
    out = p.run_turn(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert out.text == "3,142 users."
    assert out.tool_calls == []


def test_run_turn_parses_tool_use_block_as_tool_call():
    client = MagicMock()
    client.messages.create.return_value = _message(
        [_block_tool_use("toolu_1", "run_sql", {"sql": "SELECT 1"})],
        stop_reason="tool_use",
    )
    p = AnthropicProvider(model="claude-sonnet-4-6", client=client)
    out = p.run_turn(
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "run_sql", "description": "...", "input_schema": {}}],
    )
    assert out.text is None
    assert len(out.tool_calls) == 1
    assert out.tool_calls[0].id == "toolu_1"
    assert out.tool_calls[0].name == "run_sql"
    assert out.tool_calls[0].arguments == {"sql": "SELECT 1"}


def test_run_turn_handles_mixed_text_and_tool_use():
    client = MagicMock()
    client.messages.create.return_value = _message([
        _block_text("Let me check that."),
        _block_tool_use("toolu_2", "run_sql", {"sql": "SELECT count(*) FROM users"}),
    ], stop_reason="tool_use")
    p = AnthropicProvider(model="claude-sonnet-4-6", client=client)
    out = p.run_turn(
        messages=[{"role": "user", "content": "go"}],
        tools=[{"name": "run_sql", "description": "...", "input_schema": {}}],
    )
    assert out.text == "Let me check that."
    assert len(out.tool_calls) == 1


def test_run_turn_extracts_system_messages_into_top_level_kwarg():
    """role:system entries become the `system=` kwarg; they must NOT appear
    in the messages list passed to the Messages API."""
    client = MagicMock()
    client.messages.create.return_value = _message([_block_text("ok")])
    p = AnthropicProvider(model="claude-sonnet-4-6", client=client)
    p.run_turn(
        messages=[
            {"role": "system", "content": "You are X."},
            {"role": "user", "content": "hi"},
        ],
        tools=[],
    )
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"] == "You are X."
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]


def test_encode_user_message_returns_simple_role_content():
    p = AnthropicProvider(model="claude-sonnet-4-6", client=MagicMock())
    assert p.encode_user_message("hello") == {"role": "user", "content": "hello"}


def test_encode_tool_result_returns_anthropic_tool_result_block():
    p = AnthropicProvider(model="claude-sonnet-4-6", client=MagicMock())
    msg = p.encode_tool_result("toolu_42", "result text")
    assert msg == {
        "role": "user",
        "content": [{
            "type": "tool_result",
            "tool_use_id": "toolu_42",
            "content": "result text",
        }],
    }
