"""Agent loop: caps, tool orchestration, branch lifecycle."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from agent_sandbox.db import run_sql
from agent_sandbox.keon import (
    create_branch,
    delete_branch,
    find_branch_id,
    get_branch_url,
)
from agent_sandbox.output import event
from agent_sandbox.providers.base import Provider


@dataclass(slots=True)
class LoopOptions:
    question: str
    provider_name: str
    model: str | None
    max_queries: int = 10
    max_wall_s: int = 120
    row_cap: int = 1000
    always_delete: bool = False
    project: str = ""
    branch_name: str = ""


@dataclass(slots=True)
class QueryRecord:
    iteration: int
    sql: str
    rows_returned: int
    rows_truncated: bool
    duration_ms: int
    result_preview: list[Any]
    error: str | None


@dataclass(slots=True)
class LoopResult:
    answer: str
    queries: list[QueryRecord]
    cap_hit: str | None
    provider: str
    model: str
    branch_name: str
    branch_id: str
    branch_url: str | None
    branch_created_in_ms: int
    branch_deleted: bool
    branch_delete_skipped_reason: str | None
    total_duration_ms: int


_SYSTEM_PROMPT = """You are given a temporary fork of a production Postgres database.
You can run any SQL against the fork using the `run_sql` tool — including
DELETE, DROP, ALTER, CREATE INDEX. The fork will be destroyed when you finish.

You don't know the schema yet. Use `run_sql` to introspect (for example
`SELECT table_name FROM information_schema.tables WHERE table_schema='public'`,
or `SELECT column_name, data_type FROM information_schema.columns WHERE table_name='users'`).

When you can answer the user's question, stop calling tools and respond with
the answer in plain English. Cite the SQL that supports your answer."""


_RUN_SQL_TOOL_ANTHROPIC = {
    "name": "run_sql",
    "description": (
        "Run a single SQL statement against the disposable fork. Returns rows up to "
        "a cap, or the row count for DELETE/UPDATE/INSERT/DDL. Errors are returned "
        "as text so you can react."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "One SQL statement. Multi-statement strings are rejected.",
            },
        },
        "required": ["sql"],
    },
}

_RUN_SQL_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": _RUN_SQL_TOOL_ANTHROPIC["description"],
        "parameters": _RUN_SQL_TOOL_ANTHROPIC["input_schema"],
    },
}


def _fork_branch(project: str, name: str) -> tuple[str, str, int]:
    parent = find_branch_id(project=project, name="main")
    branch = create_branch(project=project, name=name, parent_id=parent)
    url = get_branch_url(project=project, branch=branch.name)
    return branch.id, url, branch.created_in_ms


def _open_connection(url: str):  # pragma: no cover — thin wrapper, exercised live
    import psycopg
    return psycopg.connect(url, autocommit=True)


def _delete_branch(branch_id: str) -> None:
    delete_branch(branch_id=branch_id)


def _tool_for_provider(provider_name: str) -> dict:
    return _RUN_SQL_TOOL_OPENAI if provider_name == "openai" else _RUN_SQL_TOOL_ANTHROPIC


def _format_tool_result(r) -> str:
    if r.error:
        return f"ERROR: {r.error}"
    if not r.result_preview:
        return f"OK. rows_affected={r.rows_returned}, duration_ms={r.duration_ms}"
    truncated_note = (
        f" (truncated, showing first {len(r.result_preview)} of {r.rows_returned})"
        if r.rows_truncated else ""
    )
    head = f"rows={r.rows_returned}, duration_ms={r.duration_ms}{truncated_note}\n"
    preview = r.result_preview[:50]
    body = "\n".join(str(row) for row in preview)
    return head + body


def _append_assistant_tool_call(messages: list[dict], provider_name: str, call) -> None:
    """Add the assistant turn that originated the tool call to the transcript
    in whatever shape the provider expects."""
    if provider_name == "anthropic":
        messages.append({
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": call.arguments,
            }],
        })
    else:
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                },
            }],
        })


def run_ask(opts: LoopOptions, *, provider: Provider) -> LoopResult:
    """Run a single agent question against a fresh fork."""
    overall_start = time.monotonic()
    branch_id, branch_url, branch_created_in_ms = _fork_branch(opts.project, opts.branch_name)
    event("branch forked", id=branch_id, duration_ms=branch_created_in_ms)

    conn = _open_connection(branch_url)
    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        provider.encode_user_message(opts.question),
    ]
    tool_spec = _tool_for_provider(provider.name)

    queries: list[QueryRecord] = []
    cap_hit: str | None = None
    final_answer: str | None = None

    iteration = 0
    while iteration < opts.max_queries:
        iteration += 1
        turn = provider.run_turn(messages=messages, tools=[tool_spec])

        if turn.tool_calls:
            for call in turn.tool_calls:
                sql = (call.arguments or {}).get("sql", "")
                event("run_sql", sql=sql.replace("\n", " ")[:120])
                r = run_sql(conn, sql, row_cap=opts.row_cap)
                event("run_sql done", rows=r.rows_returned, duration_ms=r.duration_ms)
                queries.append(QueryRecord(
                    iteration=iteration,
                    sql=sql,
                    rows_returned=r.rows_returned,
                    rows_truncated=r.rows_truncated,
                    duration_ms=r.duration_ms,
                    result_preview=r.result_preview,
                    error=r.error,
                ))
                _append_assistant_tool_call(messages, provider.name, call)
                messages.append(provider.encode_tool_result(call.id, _format_tool_result(r)))
            if (time.monotonic() - overall_start) > opts.max_wall_s:
                cap_hit = "max_wall_s"
                break
            continue

        final_answer = turn.text or ""
        break

    if final_answer is None and cap_hit is None:
        cap_hit = "max_queries"

    if cap_hit is not None and final_answer is None:
        event("cap_hit", reason=cap_hit)
        messages.append(provider.encode_user_message(
            f"You've hit the budget cap ({cap_hit}). Summarize what you found so far. "
            "No more tool calls."
        ))
        summary = provider.run_turn(messages=messages, tools=[])
        final_answer = summary.text or "(no answer)"

    deleted = False
    delete_skipped_reason: str | None = None
    if cap_hit is None or opts.always_delete:
        try:
            _delete_branch(branch_id)
            deleted = True
            event("branch deleted", id=branch_id)
        except Exception as e:  # noqa: BLE001
            delete_skipped_reason = f"delete failed: {e}"
    else:
        delete_skipped_reason = f"cap_hit: {cap_hit}"

    total_ms = int((time.monotonic() - overall_start) * 1000)
    return LoopResult(
        answer=final_answer or "",
        queries=queries,
        cap_hit=cap_hit,
        provider=provider.name,
        model=provider.model,
        branch_name=opts.branch_name,
        branch_id=branch_id,
        branch_url=branch_url,
        branch_created_in_ms=branch_created_in_ms,
        branch_deleted=deleted,
        branch_delete_skipped_reason=delete_skipped_reason,
        total_duration_ms=total_ms,
    )
