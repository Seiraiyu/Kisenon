"""Thin wrappers around the `keon` CLI (trimmed copy of agent-sandbox/keon.py).

  branches create -> {"branch": {"id", "name", ...}, ...}
  connection-string -> {"connection_string": "..."}
  branches delete --cascade <id>
"""
from __future__ import annotations

import json
import subprocess


class KeonError(RuntimeError):
    """`keon` exited non-zero or returned an unexpected shape."""


class KeonNotFound(KeonError):
    """`keon` binary isn't on PATH."""


def _run_keon(args: list[str]) -> str:
    try:
        proc = subprocess.run(["keon", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise KeonNotFound(
            "`keon` is not on PATH. Install via `curl -fsSL https://kisenon.com/install.sh | bash`."
        ) from e
    if proc.returncode != 0:
        raise KeonError(
            f"`keon {' '.join(args)}` failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    return proc.stdout


def create_branch(*, project: str, name: str) -> str:
    """Fork the project's main branch; blocks until the fork is ready. Returns the branch id."""
    out = _run_keon([
        "branches", "create", "--project", project, "--name", name, "--wait", "60", "-o", "json",
    ])
    branch_id = json.loads(out).get("branch", {}).get("id")
    if not branch_id:
        raise KeonError(f"`keon branches create` returned no branch id: {out.strip()[:200]}")
    return str(branch_id)


def get_branch_url(*, project: str, branch: str) -> str:
    data = json.loads(_run_keon(["connection-string", branch, "--project", project, "-o", "json"]))
    url = data.get("connection_string")
    if not url:
        raise KeonError(f"`keon connection-string` returned no connection_string: {data!r}")
    return url


def delete_branch(*, branch_id: str) -> None:
    _run_keon(["branches", "delete", "--cascade", branch_id])
