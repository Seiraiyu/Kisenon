"""Anthropic calls: answer with recalled facts, and extract durable facts from a message."""
from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_MODEL = "claude-sonnet-5"

EXTRACT_PROMPT = (
    "Extract durable facts about the user from their message: identity, preferences, plans, "
    "constraints, relationships. Ignore small talk and questions. Return ONLY a JSON array of "
    'short third-person strings, e.g. ["User is vegetarian"]. Return [] if nothing is worth '
    "remembering long-term."
)


def make_client() -> Any | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    return anthropic.Anthropic()


def _text(resp: Any) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def parse_facts(text: str) -> list[str]:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end < start:
        return []
    try:
        items = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [s.strip() for s in items if isinstance(s, str) and s.strip()]


def extract_facts(client: Any, model: str, message: str) -> list[str]:
    resp = client.messages.create(
        model=model, max_tokens=512, system=EXTRACT_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    return parse_facts(_text(resp))


def reply(
    client: Any, model: str, message: str, facts: list[str], history: list[tuple[str, str]],
) -> str:
    remembered = "\n".join(f"- {f}" for f in facts) or "(nothing yet)"
    system = (
        "You are a helpful assistant with long-term memory. Use what you remember when it is "
        f"relevant; don't recite it otherwise.\nWhat you remember about the user:\n{remembered}"
    )
    messages = [{"role": r, "content": c} for r, c in history]
    messages.append({"role": "user", "content": message})
    resp = client.messages.create(model=model, max_tokens=1024, system=system, messages=messages)
    return _text(resp)
