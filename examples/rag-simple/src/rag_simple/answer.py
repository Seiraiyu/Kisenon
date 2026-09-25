"""Prompt building, citation formatting, and the (optional) Claude call."""
from __future__ import annotations

from typing import Any

MODEL = "claude-sonnet-5"
SYSTEM = (
    "Answer the question using only the numbered sources. Cite every claim with the "
    "source number in square brackets, e.g. [1] or [2][3]. If the sources don't contain "
    "the answer, say so."
)


def format_context(hits: list[dict]) -> str:
    return "\n\n".join(f"[{i}] ({h['source']})\n{h['text']}" for i, h in enumerate(hits, 1))


def format_sources(hits: list[dict]) -> str:
    return "\n".join(
        f"[{i}] {h['source']} (chunk {h['ord']}, score {h['score']})" for i, h in enumerate(hits, 1)
    )


def answer(question: str, hits: list[dict], client: Any = None) -> str:
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM,
        output_config={"effort": "low"},
        messages=[{
            "role": "user",
            "content": f"Sources:\n\n{format_context(hits)}\n\nQuestion: {question}",
        }],
    )
    if resp.stop_reason == "refusal":
        return "(the model declined to answer this question)"
    return "".join(b.text for b in resp.content if b.type == "text").strip()
