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


def list_branches(*, project: str) -> list[Branch]:
    """Return all branches for a project."""
    out = _run_keon([
        "branches", "list",
        "--project", project,
        "-o", "json",
    ])
    data = json.loads(out)
    items = data.get("items", data) if isinstance(data, dict) else data
    return [
        Branch(name=item.get("name", ""), id=str(item.get("id", "")))
        for item in items
    ]


def find_branch_id(*, project: str, name: str) -> str:
    """Resolve a branch name to its id. `keon branches create --parent-id`
    requires an id, not a name."""
    for b in list_branches(project=project):
        if b.name == name:
            return b.id
    raise KeonError(f"no branch named {name!r} in project {project}")


def create_branch(*, project: str, name: str, parent_id: str) -> Branch:
    started = time.monotonic()
    out = _run_keon([
        "branches", "create",
        "--project", project,
        "--name", name,
        "--parent-id", parent_id,
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
    for key in ("connection_uri", "url", "connection_string", "uri", "connectionString"):
        if key in data and data[key]:
            return data[key]
    raise KeonError(f"`keon connection-string` returned no URL field: {data!r}")


def delete_branch(*, branch_id: str) -> None:
    """`keon branches delete <id>` takes a positional id; no --project flag."""
    _run_keon(["branches", "delete", branch_id])
