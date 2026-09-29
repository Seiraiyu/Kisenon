from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from parallel_agents.llm import DEFAULT_MODELS, LLMError, complete, extract_json


def _anthropic_response(text: str, stop_reason: str = "end_turn"):
    return SimpleNamespace(stop_reason=stop_reason,
                           content=[SimpleNamespace(type="text", text=text)])


def test_default_models():
    assert DEFAULT_MODELS == {"anthropic": "claude-sonnet-5", "openai": "gpt-5.1"}


def test_anthropic_path():
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response("hi")
    assert complete("anthropic", "claude-sonnet-5", "s", "u", client=client) == "hi"
    assert client.messages.create.call_args.kwargs["system"] == "s"


def test_anthropic_refusal_raises():
    client = MagicMock()
    client.messages.create.return_value = _anthropic_response("", "refusal")
    with pytest.raises(LLMError, match="declined"):
        complete("anthropic", "claude-sonnet-5", "s", "u", client=client)


def test_openai_path():
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
    assert complete("openai", "gpt-5.1", "s", "u", client=client) == "ok"


def test_extract_json_from_fence_and_bare():
    assert extract_json('Sure:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('{"b": [1, 2]}') == {"b": [1, 2]}


def test_extract_json_rejects_garbage():
    with pytest.raises(LLMError, match="did not return JSON"):
        extract_json("no json here")
