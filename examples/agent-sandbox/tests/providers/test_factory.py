import pytest

from agent_sandbox.providers import get_provider
from agent_sandbox.providers.anthropic_provider import AnthropicProvider
from agent_sandbox.providers.openai_provider import OpenAIProvider


def test_get_provider_anthropic_returns_anthropic_instance(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    p = get_provider("anthropic", model=None)
    assert isinstance(p, AnthropicProvider)
    assert p.model == "claude-sonnet-4-6"


def test_get_provider_anthropic_with_explicit_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    p = get_provider("anthropic", model="claude-opus-4-8")
    assert p.model == "claude-opus-4-8"


def test_get_provider_openai_returns_openai_instance(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    p = get_provider("openai", model=None)
    assert isinstance(p, OpenAIProvider)
    assert p.model == "gpt-5.1"


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown provider"):
        get_provider("cohere", model=None)
