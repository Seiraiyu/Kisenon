"""Output helpers for branch-test.

Convention:
  - JSON to stdout by default.
  - --pretty switches stdout to a caller-supplied formatter.
  - Errors are JSON on stderr; process exits.
  - tail_truncate keeps the last N bytes of subprocess output so JSON
    stays small but the agent still gets the last useful chunk.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable


def output_json(data: Any) -> None:
    sys.stdout.write(json.dumps(data, default=_json_default))
    sys.stdout.write("\n")
    sys.stdout.flush()


def output_pretty(data: Any, formatter: Callable[[Any], str]) -> None:
    text = formatter(data)
    sys.stdout.write(text)
    if not text.endswith("\n"):
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


def tail_truncate(text: str, *, cap_bytes: int = 8192) -> tuple[str, bool]:
    """Keep the last cap_bytes of `text` (counting UTF-8 bytes).

    Returns (text_or_tail, truncated_flag). Decodes safely so we don't
    return a string with a half-character at the start.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= cap_bytes:
        return text, False
    tail = encoded[-cap_bytes:]
    return tail.decode("utf-8", errors="replace"), True


def _json_default(o: Any) -> Any:
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "__dict__"):
        return o.__dict__
    raise TypeError(f"not serializable: {type(o)!r}")
