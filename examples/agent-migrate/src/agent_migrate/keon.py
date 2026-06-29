"""Thin wrappers around the `keon sandbox` CLI verbs.

Requires a `keon` build that includes the sandbox command group (the sandbox
surface is control-plane–backed and ships dormant behind a server flag).

Observed JSON shapes:
  sandbox run     -> {"sandbox_id","status","steps":[...],"promote_preview":[...],"promote_hint"}
                     (exit 1 on a "red" verdict, but stdout is still valid JSON)
  sandbox promote -> {"sandbox":{"id","status",...}}   status: promoted | awaiting_approval
  sandbox approve -> {"sandbox":{"id","status":"promoted",...}}
  sandbox discard -> {"sandbox":{"id","status":"discarded",...}}
  sandbox log     -> {"actions":[...],"max_seq":N}
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field


class KeonError(RuntimeError):
    """`keon` exited non-zero with no parseable JSON, or returned a bad shape."""


class KeonNotFound(KeonError):
    """`keon` binary isn't on PATH."""


class SandboxUnavailable(KeonError):
    """This keon build lacks `sandbox`, or the region has it disabled (501)."""


@dataclass(slots=True)
class SandboxRunResult:
    sandbox_id: str
    status: str  # "green" | "red"
    steps: list[dict]
    promote_preview: list[dict]
    promote_hint: str
    raw: dict = field(default_factory=dict)

    @property
    def green(self) -> bool:
        return self.status == "green"

    def failing_step(self) -> dict | None:
        for s in self.steps:
            if s.get("exit_code", 0) != 0 or s.get("timed_out"):
                return s
        return None


def _run(args: list[str]) -> tuple[str, str, int]:
    try:
        proc = subprocess.run(
            ["keon", *args], capture_output=True, text=True, check=False,
        )
    except FileNotFoundError as e:
        raise KeonNotFound(
            "`keon` is not on PATH. Install via "
            "`curl -fsSL https://kisenon.com/install.sh | bash`."
        ) from e
    return proc.stdout, proc.stderr, proc.returncode


def _maybe_unavailable(stdout: str, stderr: str) -> None:
    blob = f"{stdout}\n{stderr}".lower()
    if "unknown command" in blob and "sandbox" in blob:
        raise SandboxUnavailable(
            "this `keon` build has no `sandbox` command. Rebuild/upgrade keon to "
            "a version that includes `keon sandbox`."
        )
    if "not_implemented" in blob or "not yet available in this region" in blob:
        raise SandboxUnavailable(
            "sandboxes are not enabled for this region/project. Ask your Kisenon "
            "operator to enable the sandbox feature."
        )


def _run_json(args: list[str], *, allow_nonzero: bool) -> dict:
    stdout, stderr, rc = _run(args)
    if rc != 0:
        _maybe_unavailable(stdout, stderr)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise KeonError(
            f"`keon {' '.join(args)}` failed ({rc}): {(stderr or stdout).strip()[:300]}"
        ) from e
    if rc != 0 and not allow_nonzero:
        raise KeonError(f"`keon {' '.join(args)}` failed ({rc}): {(stderr or stdout).strip()[:300]}")
    return data


def sandbox_run(
    *, project: str, parent: str | None, migrate_cmd: str,
    verify_cmd: str | None = None, working_dir: str | None = None, timeout_s: int = 300,
) -> SandboxRunResult:
    args = ["sandbox", "run", "--project", project, "--migrate", migrate_cmd,
            "--timeout-s", str(timeout_s), "-o", "json"]
    if parent:
        args += ["--parent", parent]
    if verify_cmd:
        args += ["--verify", verify_cmd]
    if working_dir:
        args += ["--working-dir", working_dir]
    data = _run_json(args, allow_nonzero=True)  # red => exit 1 + valid JSON
    return SandboxRunResult(
        sandbox_id=data.get("sandbox_id", ""),
        status=data.get("status", ""),
        steps=data.get("steps", []),
        promote_preview=data.get("promote_preview", []),
        promote_hint=data.get("promote_hint", ""),
        raw=data,
    )


def _sandbox_one(verb: str, sandbox_id: str) -> dict:
    data = _run_json(["sandbox", verb, sandbox_id, "-o", "json"], allow_nonzero=False)
    return data.get("sandbox", data)


def sandbox_promote(*, sandbox_id: str) -> dict:
    return _sandbox_one("promote", sandbox_id)


def sandbox_approve(*, sandbox_id: str) -> dict:
    return _sandbox_one("approve", sandbox_id)


def sandbox_discard(*, sandbox_id: str) -> dict:
    return _sandbox_one("discard", sandbox_id)


def sandbox_log(*, sandbox_id: str, since: int = 0) -> list[dict]:
    args = ["sandbox", "log", sandbox_id, "-o", "json"]
    if since:
        args += ["--since", str(since)]
    data = _run_json(args, allow_nonzero=False)
    return data.get("actions", [])
