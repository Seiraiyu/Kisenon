from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from text2sql_eval.llm import DEFAULT_MODELS, KEY_ENV, LLMError, complete


def _anthropic_response(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
    )


def test_defaults():
    assert DEFAULT_MODELS == {"anthropic": "claude-sonnet-5", "openai": "gpt-5.1"}
    assert KEY_ENV == {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def test_anthropic_returns_text_blocks_only():
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response("SELECT 1")
    out = complete("anthropic", "claude-sonnet-5", "sys", "q", client=client)
    assert out == "SELECT 1"
    kw = client.messages.create.call_args.kwargs
    assert kw["system"] == "sys"
    assert kw["messages"] == [{"role": "user", "content": "q"}]


def test_anthropic_refusal_raises():
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response("", stop_reason="refusal")
    with pytest.raises(LLMError, match="declined"):
        complete("anthropic", "claude-sonnet-5", "s", "u", client=client)


def test_openai_puts_system_first():
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 2"))]
    )
    assert complete("openai", "gpt-5.1", "sys", "q", client=client) == "SELECT 2"
    msgs = client.chat.completions.create.call_args.kwargs["messages"]
    assert msgs[0] == {"role": "system", "content": "sys"}


def test_empty_text_raises():
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
    )
    with pytest.raises(LLMError, match="no text"):
        complete("openai", "gpt-5.1", "s", "u", client=client)


def test_unknown_provider():
    with pytest.raises(ValueError, match="unknown provider"):
        complete("cohere", "m", "s", "u", client=MagicMock())
