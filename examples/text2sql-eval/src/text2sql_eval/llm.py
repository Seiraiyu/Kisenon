"""One-shot LLM call. Anthropic by default, OpenAI optional.

No tool use here: the model writes one SQL statement and the harness runs it.
"""
from __future__ import annotations

from typing import Any

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5", "openai": "gpt-5.1"}
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


class LLMError(RuntimeError):
    """The model declined, or returned nothing usable."""


def complete(provider: str, model: str, system: str, user: str, *, client: Any = None) -> str:
    if provider == "anthropic":
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if resp.stop_reason == "refusal":
            raise LLMError(f"{model} declined the request")
        text = "".join(b.text for b in resp.content if b.type == "text")
    elif provider == "openai":
        if client is None:
            import openai
            client = openai.OpenAI()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.choices[0].message.content or ""
    else:
        raise ValueError(f"unknown provider: {provider!r}. Known: anthropic, openai.")
    if not text.strip():
        raise LLMError(f"{model} returned no text")
    return text
