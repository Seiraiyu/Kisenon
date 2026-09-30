"""stderr progress events, stdout human text + one JSON line (agent-sandbox convention)."""
from __future__ import annotations

import json
import sys
from typing import Any


def event(label: str, **fields: Any) -> None:
    """`[label]` or `[label: first_value | k=v | ...]` on stderr."""
    if not fields:
        line = f"[{label}]"
    else:
        items = list(fields.items())
        tail = " | ".join(f"{k}={v}" for k, v in items[1:])
        line = f"[{label}: {items[0][1]}" + (f" | {tail}" if tail else "") + "]"
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def output_json(data: Any) -> None:
    sys.stdout.write(json.dumps(data, default=str) + "\n")
    sys.stdout.flush()


def output_error(message: str, extra: dict[str, Any] | None = None, *, exit_code: int = 1) -> None:
    sys.stderr.write(json.dumps({"error": message, **(extra or {})}) + "\n")
    sys.stderr.flush()
    sys.exit(exit_code)
