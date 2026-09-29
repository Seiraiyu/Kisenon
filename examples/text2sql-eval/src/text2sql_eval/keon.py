"""Thin wrappers around the `keon` CLI (target: 0.1.29).

Same contract as branch-test/kisenon.py; re-implemented here so the example
is self-contained. Current shapes of the keon JSON responses:

  branches list   -> {"branches": [...], "pagination": {}}
  branches create -> {"branch": {"id", "name", ...}, "operations": []}
  connection-string -> {"connection_string": "...", "connection_uri": "..."}
  branches delete --cascade <id> -> {"ok": true, "id": "..."}
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


class KeonError(RuntimeError):
    """`keon` ran but exited non-zero, or returned an unexpected shape."""


class KeonNotFound(KeonError):
    """`keon` binary isn't on PATH."""


@dataclass(slots=True)
class Branch:
    name: str
    id: str
    created_in_ms: int = 0


def _run_keon(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["keon", *args], capture_output=True, text=True, check=False,
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
    out = _run_keon(["branches", "list", "--project", project, "-o", "json"])
    data = json.loads(out)
    return [
        Branch(name=item.get("name", ""), id=str(item.get("id", "")))
        for item in data.get("branches", [])
    ]


def find_branch_id(*, project: str, name: str) -> str:
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
        "--wait",
        "-o", "json",
    ])
    elapsed_ms = int((time.monotonic() - started) * 1000)
    payload = json.loads(out)
    branch = payload.get("branch", {})
    return Branch(
        name=branch.get("name", name),
        id=str(branch.get("id", "")),
        created_in_ms=elapsed_ms,
    )


def get_branch_url(*, project: str, branch: str) -> str:
    out = _run_keon([
        "connection-string", branch,
        "--project", project,
        "-o", "json",
    ])
    data = json.loads(out)
    url = data.get("connection_string")
    if not url:
        raise KeonError(f"`keon connection-string` returned no connection_string: {data!r}")
    return url


def delete_branch(*, branch_id: str) -> None:
    """`keon branches delete --cascade <id>` — cascades through any attached
    endpoints (Kisenon issue #4: `--cascade` is the official knob)."""
    _run_keon(["branches", "delete", "--cascade", branch_id])


def reset_branch(*, branch_id: str) -> None:
    """`keon branches reset <id>`: roll the branch back to its parent's HEAD.
    Same id and connection string afterwards; keon polls until it's done."""
    _run_keon(["branches", "reset", branch_id, "-o", "json"])


@contextmanager
def forked(*, project: str, name: str, keep: bool = False) -> Iterator[tuple[Branch, str]]:
    """Fork `main` as `name`, yield (branch, connection_url), delete on exit
    unless `keep`. A failed delete prints the manual cleanup command."""
    parent = find_branch_id(project=project, name="main")
    branch = create_branch(project=project, name=name, parent_id=parent)
    try:
        yield branch, get_branch_url(project=project, branch=branch.name)
    finally:
        if not keep:
            try:
                delete_branch(branch_id=branch.id)
            except KeonError as e:
                sys.stderr.write(
                    f"[cleanup failed: {e}] run: keon branches delete --cascade {branch.id}\n"
                )
