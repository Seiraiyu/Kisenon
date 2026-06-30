"""OpenAI provider — wraps Chat Completions for tool-use."""
from __future__ import annotations

import json
from typing import Any

from agent_migrate.providers.base import ToolCall, TurnResult

DEFAULT_MODEL = "gpt-5.1"


class OpenAIProvider:
    name = "openai"

    def __init__(self, *, model: str = DEFAULT_MODEL, client: Any | None = None) -> None:
        self.model = model
        if client is None:
            import openai
            client = openai.OpenAI()
        self._client = client

    def run_turn(self, messages: list[dict], tools: list[dict]) -> TurnResult:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message
        tool_calls: list[ToolCall] = []
        for tc in (message.tool_calls or []):
            args_raw = tc.function.arguments or "{}"
            try:
                arguments = json.loads(args_raw)
            except json.JSONDecodeError:
                arguments = {"_raw": args_raw}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=arguments))
        text = message.content if not tool_calls else None
        return TurnResult(
            text=text,
            tool_calls=tool_calls,
            raw={
                "id": getattr(response, "id", None),
                "finish_reason": getattr(choice, "finish_reason", None),
                "model": getattr(response, "model", None),
            },
        )

    def encode_user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def encode_tool_result(self, tool_call_id: str, result_text: str) -> dict:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result_text}
