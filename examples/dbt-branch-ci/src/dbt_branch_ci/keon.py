"""Thin wrappers around the `keon` CLI (copied from agent-sandbox, trimmed).

  branches list     -> {"branches": [...], "pagination": {}}
  branches create   -> {"branch": {"id", "name", ...}, "operations": []}
  connection-string -> {"connection_string": "..."}
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


class KeonError(RuntimeError):
    """`keon` ran but exited non-zero, or returned an unexpected shape."""


class KeonNotFound(KeonError):
    """`keon` binary isn't on PATH."""


@dataclass(slots=True)
class Branch:
    name: str
    id: str


def _run_keon(args: list[str]) -> str:
    try:
        proc = subprocess.run(["keon", *args], capture_output=True, text=True, check=False)
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


def find_branch_id(*, project: str, name: str) -> str:
    data = json.loads(_run_keon(["branches", "list", "--project", project, "-o", "json"]))
    for item in data.get("branches", []):
        if item.get("name") == name:
            return str(item["id"])
    raise KeonError(f"no branch named {name!r} in project {project}")


def create_branch(*, project: str, name: str, parent_id: str) -> Branch:
    out = _run_keon([
        "branches", "create", "--project", project, "--name", name,
        "--parent-id", parent_id, "--wait", "-o", "json",
    ])
    branch = json.loads(out).get("branch", {})
    return Branch(name=branch.get("name", name), id=str(branch.get("id", "")))


def get_branch_url(*, project: str, branch: str) -> str:
    data = json.loads(_run_keon(["connection-string", branch, "--project", project, "-o", "json"]))
    url = data.get("connection_string")
    if not url:
        raise KeonError(f"`keon connection-string` returned no connection_string: {data!r}")
    return url


def delete_branch(*, branch_id: str) -> None:
    _run_keon(["branches", "delete", "--cascade", branch_id])
