"""Orchestrator: drives the keon/pg_dump/subprocess sequence for one run."""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from branch_test.kisenon import (
    Branch,
    KeonError,
    KeonNotFound,
    create_branch,
    delete_branch,
    get_branch_url,
)
from branch_test.output import tail_truncate
from branch_test.schema_diff import (
    PgDumpNotFound,
    capture_schema,
    compute_diff,
)


_TIMEOUT_EXIT_CODE = 124  # GNU `timeout` convention


@dataclass(slots=True)
class StepResult:
    name: str
    command: str
    exit_code: int
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    stdout_truncated: bool
    stderr_truncated: bool


@dataclass(slots=True)
class RunOptions:
    migrate_cmd: str
    verify_cmd: str | None
    rollback_cmd: str | None
    working_dir: str
    timeout_s: int
    schema_diff: bool = True
    branch_name: str | None = None
    keep: bool = False
    delete: bool = False


@dataclass(slots=True)
class RunResult:
    status: str  # "green" | "red"
    branch: dict[str, Any]
    steps: list[StepResult] = field(default_factory=list)
    schema_diff: dict[str, Any] | None = None
    promote_hint: dict[str, Any] | None = None


def run_step(
    *,
    name: str,
    command: str,
    env: dict[str, str],
    cwd: str,
    timeout_s: int,
) -> StepResult:
    """Run one subprocess; return its captured result."""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
        stdout = proc.stdout
        stderr = proc.stderr
        code = proc.returncode
    except subprocess.TimeoutExpired:
        stdout = ""
        stderr = f"timeout after {timeout_s}s"
        code = _TIMEOUT_EXIT_CODE

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout_tail, stdout_truncated = tail_truncate(stdout)
    stderr_tail, stderr_truncated = tail_truncate(stderr)
    return StepResult(
        name=name,
        command=command,
        exit_code=code,
        duration_ms=duration_ms,
        stdout_tail=stdout_tail,
        stderr_tail=stderr_tail,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def execute_run(
    opts: RunOptions,
    *,
    project: str,
    main_url: str,
    branch_name: str,
) -> tuple[RunResult, int]:
    """Drive the full sequence: create branch -> migrate -> (verify) -> (rollback)
    -> schema diff -> cleanup -> JSON.

    Returns (RunResult, process_exit_code).
    """
    branch: Branch | None = None
    branch_url: str | None = None
    before_schema: str | None = None
    after_schema: str | None = None
    pg_dump_skipped_reason: str | None = None

    try:
        branch = create_branch(project=project, name=branch_name, parent="main")
        branch_url = get_branch_url(project=project, branch=branch.name)
    except (KeonNotFound, KeonError) as e:
        # Couldn't even create the branch; surface error and bail.
        result = RunResult(
            status="red",
            branch={"name": branch_name, "url": None, "created_in_ms": 0,
                    "deleted": False, "delete_skipped_reason": str(e)},
        )
        return result, 1

    # Capture before-schema.
    if opts.schema_diff:
        try:
            before_schema = capture_schema(branch_url)
        except PgDumpNotFound as e:
            pg_dump_skipped_reason = str(e)
        except RuntimeError as e:
            pg_dump_skipped_reason = str(e)

    env = {"DATABASE_URL": branch_url}

    steps: list[StepResult] = []

    migrate = run_step(
        name="migrate", command=opts.migrate_cmd,
        env=env, cwd=opts.working_dir, timeout_s=opts.timeout_s,
    )
    steps.append(migrate)
    green = migrate.exit_code == 0

    if green and opts.verify_cmd:
        verify = run_step(
            name="verify", command=opts.verify_cmd,
            env=env, cwd=opts.working_dir, timeout_s=opts.timeout_s,
        )
        steps.append(verify)
        green = green and verify.exit_code == 0

    if green and opts.rollback_cmd:
        rollback = run_step(
            name="rollback", command=opts.rollback_cmd,
            env=env, cwd=opts.working_dir, timeout_s=opts.timeout_s,
        )
        steps.append(rollback)
        green = green and rollback.exit_code == 0

        # After-rollback schema only meaningful if we captured before.
        if green and opts.schema_diff and before_schema is not None:
            try:
                after_schema = capture_schema(branch_url)
            except (PgDumpNotFound, RuntimeError) as e:
                pg_dump_skipped_reason = str(e)

    schema_diff_block: dict[str, Any] | None = None
    if opts.schema_diff:
        if before_schema is None:
            schema_diff_block = {
                "captured": False,
                "reason": pg_dump_skipped_reason or "pg_dump not available",
            }
        elif after_schema is None and opts.rollback_cmd is None:
            schema_diff_block = {
                "captured": True,
                "before_after_unchanged": None,  # n/a; no rollback ran
                "unified_diff_excerpt": None,
                "note": "rollback not provided; after-schema not captured",
            }
        elif after_schema is None:
            schema_diff_block = {
                "captured": True,
                "before_after_unchanged": None,
                "unified_diff_excerpt": None,
                "note": pg_dump_skipped_reason or "after-schema capture skipped",
            }
        else:
            diff = compute_diff(before_schema, after_schema)
            schema_diff_block = {
                "captured": True,
                "before_after_unchanged": diff == "",
                "unified_diff_excerpt": diff[:4000] if diff else None,
            }

    # Cleanup policy.
    should_delete = (green and not opts.keep) or opts.delete
    deleted = False
    delete_skipped_reason: str | None = None
    if should_delete and branch is not None:
        try:
            delete_branch(project=project, branch=branch.name)
            deleted = True
        except KeonError as e:
            delete_skipped_reason = f"keon delete failed: {e}"
    elif not should_delete:
        delete_skipped_reason = "--keep" if opts.keep else "kept on red"

    promote_hint: dict[str, Any] | None = None
    if green:
        promote_hint = {
            "next_step": "If this looks right, apply against main:",
            "command": opts.migrate_cmd,
            "env": {"DATABASE_URL": main_url},
        }

    branch_block: dict[str, Any] = {
        "name": branch.name if branch else branch_name,
        "url": branch_url,
        "created_in_ms": branch.created_in_ms if branch else 0,
        "deleted": deleted,
        "delete_skipped_reason": delete_skipped_reason,
    }

    result = RunResult(
        status="green" if green else "red",
        branch=branch_block,
        steps=steps,
        schema_diff=schema_diff_block,
        promote_hint=promote_hint,
    )
    return result, 0 if green else 1


def render_pretty(result: RunResult) -> str:
    lines: list[str] = []
    lines.append(f"status: {result.status}")
    lines.append(
        f"branch: {result.branch['name']}  created_in_ms={result.branch['created_in_ms']}  "
        f"deleted={result.branch['deleted']}"
    )
    for s in result.steps:
        lines.append(f"  [{s.name}] exit={s.exit_code} duration_ms={s.duration_ms}")
        if s.exit_code != 0:
            lines.append(f"    stderr: {s.stderr_tail.strip()[:400]}")
    if result.schema_diff:
        sd = result.schema_diff
        lines.append(
            f"schema_diff: captured={sd.get('captured')} "
            f"unchanged={sd.get('before_after_unchanged')}"
        )
    if result.promote_hint:
        lines.append("promote_hint:")
        lines.append(f"  {result.promote_hint['command']}  "
                     f"DATABASE_URL=<your KISENON_URL>")
    return "\n".join(lines)


def result_as_dict(result: RunResult) -> dict[str, Any]:
    payload = {
        "status": result.status,
        "branch": result.branch,
        "steps": [asdict(s) for s in result.steps],
        "schema_diff": result.schema_diff,
    }
    if result.promote_hint is not None:
        payload["promote_hint"] = result.promote_hint
    return payload
