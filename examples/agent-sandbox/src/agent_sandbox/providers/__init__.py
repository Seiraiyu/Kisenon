"""Provider factory: name -> instance."""
from __future__ import annotations

from agent_sandbox.providers.anthropic_provider import (
    DEFAULT_MODEL as ANTHROPIC_DEFAULT_MODEL,
)
from agent_sandbox.providers.anthropic_provider import (
    AnthropicProvider,
)
from agent_sandbox.providers.base import Provider, ToolCall, TurnResult
from agent_sandbox.providers.openai_provider import (
    DEFAULT_MODEL as OPENAI_DEFAULT_MODEL,
)
from agent_sandbox.providers.openai_provider import (
    OpenAIProvider,
)

__all__ = [
    "Provider",
    "ToolCall",
    "TurnResult",
    "AnthropicProvider",
    "OpenAIProvider",
    "get_provider",
]


def get_provider(name: str, *, model: str | None) -> Provider:
    if name == "anthropic":
        return AnthropicProvider(model=model or ANTHROPIC_DEFAULT_MODEL)
    if name == "openai":
        return OpenAIProvider(model=model or OPENAI_DEFAULT_MODEL)
    raise ValueError(f"unknown provider: {name!r}. Known: anthropic, openai.")
