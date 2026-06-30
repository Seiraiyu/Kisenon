"""Iterative migration agent: inspect → propose raw SQL → keon sandbox run →
revise on red, up to a cap. The green sandbox is offered for promote."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from agent_migrate import keon
from agent_migrate.output import event
from agent_migrate.providers.base import Provider
from agent_migrate.schema import NotReadOnly, open_readonly, run_select, summarize


@dataclass(slots=True)
class LoopOptions:
    request: str
    provider_name: str
    model: str | None
    project: str
    parent: str = "main"
    kisenon_url: str = ""
    work_dir: str = ".agent_migrate_work"
    max_attempts: int = 5
    timeout_s: int = 300
    auto_promote: bool = False


@dataclass(slots=True)
class AttemptRecord:
    attempt: int
    migration_sql: str
    verify_sql: str
    sandbox_id: str
    status: str
    failing_step: str | None
    stderr_tail: str | None


@dataclass(slots=True)
class LoopResult:
    answer: str
    attempts: list[AttemptRecord]
    final_status: str  # "green" | "red" | "no_attempt"
    green_sandbox_id: str | None
    promote_preview: list[dict]
    promote_hint: str | None
    promoted: str | None  # None | "promoted" | "awaiting_approval"
    provider: str
    model: str
    total_duration_ms: int = 0


_SYSTEM_PROMPT = """You are a careful database migration engineer. The user wants a schema
change to a production Postgres database.

You have two tools:
- `inspect_schema(sql)`: run a read-only SELECT/WITH against the *live* database to
  understand the current schema and data. You cannot write here.
- `run_migration(migration_sql, verify_sql)`: apply your migration to a disposable,
  scoped *fork* of production and then run your verify check. `migration_sql` is the
  raw SQL of the change (DDL + any backfill). `verify_sql` must RAISE an exception if
  the migration did not achieve the goal (e.g. `DO $$ BEGIN IF EXISTS (SELECT 1 FROM
  orders WHERE status IS NULL) THEN RAISE EXCEPTION 'nulls remain'; END IF; END $$;`).
  A "green" result means migrate and verify both succeeded on the fork; "red" means
  one failed — read the stderr, fix your SQL, and call run_migration again.

Promote replays your captured statements inside a single transaction, so anything that
can't run in a transaction is NOT promotable. In particular, do NOT use `CREATE INDEX
CONCURRENTLY` — it succeeds on the fork but is excluded from the promote set, so the
index would never reach production. Use a plain `CREATE INDEX` (and other transactional
DDL) so everything you verify is exactly what promotes.

Production is never touched by your SQL. When you get a green result, stop and tell the
user the migration is ready and how to promote it. If you cannot get green within the
attempt budget, explain what blocked you."""


_TOOLS_ANTHROPIC = [
    {
        "name": "inspect_schema",
        "description": (
            "Run a read-only SELECT/WITH against the live database to inspect schema or data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "One SELECT/WITH statement."}},
            "required": ["sql"],
        },
    },
    {
        "name": "run_migration",
        "description": (
            "Apply migration_sql to a scoped fork, then run verify_sql; "
            "returns a green/red verdict."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "migration_sql": {
                    "type": "string",
                    "description": "Raw SQL of the migration (DDL + backfill).",
                },
                "verify_sql": {
                    "type": "string",
                    "description": "SQL that RAISEs if the goal isn't met.",
                },
            },
            "required": ["migration_sql", "verify_sql"],
        },
    },
]


def _tools_for(provider_name: str) -> list[dict]:
    if provider_name == "anthropic":
        return _TOOLS_ANTHROPIC
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in _TOOLS_ANTHROPIC
    ]


# Indirections so tests can stub the live edges.
def _open_readonly(url: str):  # pragma: no cover
    return open_readonly(url)


def _summarize(conn) -> str:  # pragma: no cover
    return summarize(conn)


def _run_select(conn, sql: str):  # pragma: no cover
    return run_select(conn, sql)


def _append_assistant_tool_call(messages, provider_name, call) -> None:
    if provider_name == "anthropic":
        messages.append({"role": "assistant", "content": [
            {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}]})
    else:
        messages.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": call.id, "type": "function",
             "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}]})


def _do_inspect(conn, sql: str) -> str:
    try:
        rows = _run_select(conn, sql)
    except NotReadOnly as e:
        return f"ERROR: {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: {e}"
    if not rows:
        return "OK (0 rows)"
    head = "\n".join(str(r) for r in rows[:50])
    return f"{len(rows)} row(s):\n{head}"


def _do_migration(
    opts, work: Path, attempt: int, migration_sql: str, verify_sql: str,
) -> tuple[AttemptRecord, keon.SandboxRunResult]:
    (work / "migration.sql").write_text(migration_sql)
    (work / "verify.sql").write_text(verify_sql)
    migrate_cmd = 'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migration.sql'
    verify_cmd = 'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f verify.sql'
    event("run_migration", attempt=attempt)
    r = keon.sandbox_run(
        project=opts.project, parent=opts.parent,
        migrate_cmd=migrate_cmd, verify_cmd=verify_cmd,
        working_dir=str(work), timeout_s=opts.timeout_s,
    )
    fs = r.failing_step()
    event("verdict", status=r.status, sandbox=r.sandbox_id)
    rec = AttemptRecord(
        attempt=attempt, migration_sql=migration_sql, verify_sql=verify_sql,
        sandbox_id=r.sandbox_id, status=r.status,
        failing_step=(fs or {}).get("name") if fs else None,
        stderr_tail=(fs or {}).get("stderr_tail") if fs else None,
    )
    return rec, r


def _migration_feedback(r: keon.SandboxRunResult) -> str:
    if r.green:
        n = len(r.promote_preview)
        return (f"GREEN. sandbox={r.sandbox_id}; {n} replayable statement(s) ready to promote. "
                f"Promote with: {r.promote_hint}. Stop here and tell the user.")
    fs = r.failing_step() or {}
    return (f"RED. step `{fs.get('name')}` failed (exit {fs.get('exit_code')}). "
            f"stderr:\n{fs.get('stderr_tail') or '(none)'}\n"
            "Fix the SQL and try run_migration again.")


def run_ask(opts: LoopOptions, *, provider: Provider) -> LoopResult:
    start = time.monotonic()
    conn = _open_readonly(opts.kisenon_url)
    work = Path(opts.work_dir)
    work.mkdir(parents=True, exist_ok=True)

    schema_text = _summarize(conn)
    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        provider.encode_user_message(
            f"Current schema:\n{schema_text}\n\nRequest: {opts.request}"),
    ]
    tools = _tools_for(provider.name)

    attempts: list[AttemptRecord] = []
    green: keon.SandboxRunResult | None = None
    final_answer: str | None = None

    while True:
        turn = provider.run_turn(messages=messages, tools=tools)
        if not turn.tool_calls:
            final_answer = turn.text or ""
            break

        for call in turn.tool_calls:
            args = call.arguments or {}
            if call.name == "inspect_schema":
                result_text = _do_inspect(conn, args.get("sql", ""))
            elif call.name == "run_migration":
                rec, r = _do_migration(
                    opts, work, len(attempts) + 1,
                    args.get("migration_sql", ""), args.get("verify_sql", ""))
                attempts.append(rec)
                if r.green and green is None:
                    green = r
                result_text = _migration_feedback(r)
            else:
                result_text = f"ERROR: unknown tool {call.name}"
            _append_assistant_tool_call(messages, provider.name, call)
            messages.append(provider.encode_tool_result(call.id, result_text))

        if green is not None:
            # Let the model produce a closing message, but it may also just stop.
            pass
        if len([a for a in attempts]) >= opts.max_attempts and green is None:
            messages.append(provider.encode_user_message(
                f"You've used all {opts.max_attempts} migration attempts without a green result. "
                "Summarize what blocked you. No more tool calls."))
            final_answer = provider.run_turn(messages=messages, tools=[]).text or "(no answer)"
            break

    if final_answer is None:
        final_answer = ""

    if green is not None:
        final_status = "green"
    elif attempts:
        final_status = "red"
    else:
        final_status = "no_attempt"

    promoted: str | None = None
    if green is not None and opts.auto_promote:
        event("auto-promote", sandbox=green.sandbox_id)
        sb = keon.sandbox_promote(sandbox_id=green.sandbox_id)
        promoted = sb.get("status")

    return LoopResult(
        answer=final_answer,
        attempts=attempts,
        final_status=final_status,
        green_sandbox_id=green.sandbox_id if green else None,
        promote_preview=green.promote_preview if green else [],
        promote_hint=green.promote_hint if green else None,
        promoted=promoted,
        provider=provider.name,
        model=provider.model,
        total_duration_ms=int((time.monotonic() - start) * 1000),
    )
