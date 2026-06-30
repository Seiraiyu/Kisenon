"""Anthropic provider — wraps the Messages API for tool-use."""
from __future__ import annotations

from typing import Any

from agent_sandbox.providers.base import ToolCall, TurnResult

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, model: str = DEFAULT_MODEL, client: Any | None = None) -> None:
        self.model = model
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self._client = client

    def run_turn(self, messages: list[dict], tools: list[dict]) -> TurnResult:
        system_text, conv_messages = _split_system(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "messages": conv_messages,
        }
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = tools
        response = self._client.messages.create(**kwargs)
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(getattr(block, "text", ""))
            elif btype == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=dict(block.input or {}),
                ))
        return TurnResult(
            text="".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            raw={
                "id": getattr(response, "id", None),
                "stop_reason": getattr(response, "stop_reason", None),
                "model": getattr(response, "model", None),
            },
        )

    def encode_user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def encode_tool_result(self, tool_call_id: str, result_text: str) -> dict:
        return {
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": result_text,
            }],
        }


def _split_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Anthropic Messages API takes `system` as a top-level kwarg, not as a
    role:system message. Pull any system messages out of the list and join
    them into a single string."""
    system_chunks: list[str] = []
    conv: list[dict] = []
    for m in messages:
        if m.get("role") == "system":
            content = m.get("content", "")
            if isinstance(content, str):
                system_chunks.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        system_chunks.append(block.get("text", ""))
        else:
            conv.append(m)
    system_text = "\n\n".join(s for s in system_chunks if s) or None
    return system_text, conv
