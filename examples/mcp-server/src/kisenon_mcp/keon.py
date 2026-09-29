"""Thin wrappers around `keon sandbox` (target: keon 0.1.59).

  sandbox create -o json  -> {"sandbox": {"id", "status": "active", ...},
                              "sandbox_database_url": "postgresql://..."}
                             (exits non-zero if the sandbox didn't become active)
  sandbox diff <id>       -> legible schema + data diff and the raw promote preview
  sandbox discard <id>    -> {"sandbox": {"id", "status": "discarded", ...}}
"""
from __future__ import annotations

import json
import subprocess


class KeonError(RuntimeError):
    """`keon` ran but exited non-zero, or returned an unexpected shape."""


class KeonNotFound(KeonError):
    """`keon` binary isn't on PATH."""


def _run_json(args: list[str]) -> dict:
    try:
        proc = subprocess.run(["keon", *args, "-o", "json"], capture_output=True, text=True,
                              check=False)
    except FileNotFoundError as e:
        raise KeonNotFound(
            "`keon` is not on PATH. Install via "
            "`curl -fsSL https://kisenon.com/install.sh | bash`."
        ) from e
    if proc.returncode != 0:
        raise KeonError(f"`keon {' '.join(args)}` failed ({proc.returncode}): "
                        f"{(proc.stderr or proc.stdout).strip()[:300]}")
    return json.loads(proc.stdout or "{}")


def sandbox_create(*, project: str | None, ttl_s: int) -> tuple[str, str]:
    """Fork the project's main branch into a scoped sandbox. Returns (id, url).
    `--budget-wall-seconds` makes the server auto-discard it after `ttl_s`."""
    args = ["sandbox", "create", "--budget-wall-seconds", str(ttl_s)]
    if project:
        args += ["--project", project]
    data = _run_json(args)
    sandbox_id = data.get("sandbox", {}).get("id")
    url = data.get("sandbox_database_url")
    if not sandbox_id or not url:
        raise KeonError(f"`keon sandbox create` returned no id/url: {str(data)[:200]}")
    return sandbox_id, url


def sandbox_diff(sandbox_id: str) -> dict:
    return _run_json(["sandbox", "diff", sandbox_id])


def sandbox_discard(sandbox_id: str) -> None:
    _run_json(["sandbox", "discard", sandbox_id])
