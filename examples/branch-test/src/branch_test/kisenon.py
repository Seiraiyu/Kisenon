"""Thin wrappers around the `keon` CLI.

Every function shells out, parses JSON, and returns a small dataclass.
We don't depend on a Kisenon SDK because there isn't an official one yet
and `keon` is the documented surface.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass


class KeonError(RuntimeError):
    """`keon` ran but exited non-zero."""


class KeonNotFound(KeonError):
    """`keon` binary isn't on PATH."""


@dataclass(slots=True)
class Branch:
    name: str
    id: str
    created_in_ms: int = 0


def _run_keon(args: list[str]) -> str:
    """Run `keon <args>` and return stdout. Raises KeonError on failure."""
    try:
        proc = subprocess.run(
            ["keon", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise KeonNotFound(
            "`keon` is not on PATH. Install via "
            "`curl -fsSL https://kisenon.com/install.sh | bash`."
        ) from e
    if proc.returncode != 0:
        raise KeonError(
            f"`keon {' '.join(args)}` failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    return proc.stdout


def create_branch(*, project: str, name: str, parent: str = "main") -> Branch:
    started = time.monotonic()
    out = _run_keon([
        "branches", "create",
        "--project", project,
        "--name", name,
        "--parent", parent,
        "-o", "json",
    ])
    elapsed_ms = int((time.monotonic() - started) * 1000)
    data = json.loads(out)
    return Branch(
        name=data.get("name", name),
        id=str(data.get("id", "")),
        created_in_ms=elapsed_ms,
    )


def get_branch_url(*, project: str, branch: str) -> str:
    out = _run_keon([
        "connection-string", branch,
        "--project", project,
        "-o", "json",
    ])
    data = json.loads(out)
    for key in ("url", "connection_string", "uri", "connectionString"):
        if key in data and data[key]:
            return data[key]
    raise KeonError(f"`keon connection-string` returned no URL field: {data!r}")


def delete_branch(*, project: str, branch: str) -> None:
    _run_keon([
        "branches", "delete", branch,
        "--project", project,
    ])
