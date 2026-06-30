"""Provider abstraction. Anthropic and OpenAI both reduce to this shape.

`loop.py` only ever calls into a `Provider` — it never imports anthropic or
openai directly. That keeps the loop logic provider-agnostic and the tests
easy to write against a fake provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class TurnResult:
    text: str | None
    tool_calls: list[ToolCall]
    raw: dict = field(default_factory=dict)


class Provider(Protocol):
    name: str
    model: str

    def run_turn(self, messages: list[dict], tools: list[dict]) -> TurnResult: ...
    def encode_user_message(self, text: str) -> dict: ...
    def encode_tool_result(self, tool_call_id: str, result_text: str) -> dict: ...
