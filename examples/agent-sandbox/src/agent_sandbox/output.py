"""Output helpers for agent-sandbox.

Convention:
  - Per-step events stream to stderr in `[label: value | key=value]` form so
    a human watching along sees what the agent did.
  - Final answer prints to stdout as `Answer: <text>`.
  - Full JSON record prints to stdout on a single line, pipeable to `jq`.
  - Fatal errors are JSON on stderr; process exits.
"""
from __future__ import annotations

import base64
import json
import sys
from decimal import Decimal
from typing import Any
from uuid import UUID


def event(label: str, **fields: Any) -> None:
    """Stream a structured `[label: ...]` event to stderr.

    Shape rules:
      event("done")                                  -> [done]
      event("forking branch", duration_ms=547)       -> [forking branch: 547ms]
      event("run_sql", sql="SELECT 1", rows=1, d=8)  -> [run_sql: SELECT 1 | rows=1 | d=8]

    The first kwarg's value renders bare (no `key=`). Subsequent kwargs render
    `key=value`, pipe-separated. The lone-`duration_ms` case gets the human
    `Nms` shorthand because it's by far the most common single-field event.
    """
    if not fields:
        line = f"[{label}]"
    elif len(fields) == 1 and "duration_ms" in fields:
        line = f"[{label}: {fields['duration_ms']}ms]"
    else:
        items = list(fields.items())
        head_value = items[0][1]
        tail = " | ".join(f"{k}={v}" for k, v in items[1:])
        body = f"{head_value}" + (f" | {tail}" if tail else "")
        line = f"[{label}: {body}]"
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def print_answer(text: str) -> None:
    sys.stdout.write("Answer: " + text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()


def output_json(data: Any) -> None:
    sys.stdout.write(json.dumps(data, default=_json_default))
    sys.stdout.write("\n")
    sys.stdout.flush()


def output_error(message: str, extra: dict[str, Any] | None = None, *, exit_code: int = 1) -> None:
    payload: dict[str, Any] = {"error": message}
    if extra:
        payload.update(extra)
    sys.stderr.write(json.dumps(payload, default=_json_default))
    sys.stderr.write("\n")
    sys.stderr.flush()
    sys.exit(exit_code)


def _json_default(o: Any) -> Any:
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, UUID):
        return str(o)
    if isinstance(o, (bytes, bytearray, memoryview)):
        return {"$bytes_b64": base64.b64encode(bytes(o)).decode()}
    if hasattr(o, "__dict__"):
        return o.__dict__
    raise TypeError(f"not serializable: {type(o)!r}")
