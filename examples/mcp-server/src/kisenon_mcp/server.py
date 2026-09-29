"""kisenon-mcp: disposable Kisenon forks as MCP tools (stdio).

Safety by construction: no tool takes a connection string. Every SQL tool takes a
`fork_id` that must come from `fork_database` in this session, so `main` is
unreachable. Forks expire after KISENON_FORK_TTL_MIN (default 30) minutes, both
server-side (sandbox wall-clock budget) and here (reaped on every tool call and
on shutdown).
"""
from __future__ import annotations

import atexit
import functools
import json
import os
import re
import signal
import sys
import time
from typing import Any

import psycopg
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from psycopg.rows import dict_row

from kisenon_mcp import keon
from kisenon_mcp.forks import Fork, Registry

load_dotenv()
MAX_ROWS = 200
registry = Registry(
    project=os.environ.get("KISENON_PROJECT_ID") or None,
    ttl_s=int(os.environ.get("KISENON_FORK_TTL_MIN", "30")) * 60,
)
mcp = MCPServer(
    "kisenon-forks",
    instructions=(
        "Use fork_database to get a disposable copy of the user's Postgres database, then "
        "run_sql / explain_analyze against it freely (DDL and destructive SQL are fine: "
        "it is a fork). Use schema_diff to show what changed, destroy_fork when done."
    ),
)


def _connect(url: str) -> Any:
    return psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=30)


def _use(fork_id: str) -> Fork:
    registry.reap()
    return registry.get(fork_id)


def surfaced(fn):
    """Turn DB/keon errors into ToolErrors so the model sees the real message
    (other exceptions are masked as "Error executing tool")."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (psycopg.Error, keon.KeonError) as e:
            raise ToolError(f"{type(e).__name__}: {e}") from e

    return wrapper


def _jsonable(rows: list[dict]) -> list[dict]:
    return json.loads(json.dumps(rows, default=str))


@mcp.tool()
@surfaced
def fork_database(name: str | None = None) -> dict:
    """Fork the project's main branch into a disposable, scoped sandbox (~seconds).
    Returns {fork_id, expires_at}. `name` is an optional label for list_forks."""
    registry.reap()
    return registry.create(name).public()


@mcp.tool()
@surfaced
def run_sql(fork_id: str, sql: str) -> dict:
    """Run SQL on a fork (any statement, including DELETE/ALTER/CREATE INDEX).
    Returns up to 200 rows, the rowcount, and the duration."""
    fork = _use(fork_id)
    started = time.monotonic()
    with _connect(fork.url) as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchmany(MAX_ROWS + 1) if cur.description else []
        rowcount = cur.rowcount
    return {
        "rows": _jsonable(rows[:MAX_ROWS]),
        "truncated": len(rows) > MAX_ROWS,
        "rowcount": rowcount,
        "duration_ms": round((time.monotonic() - started) * 1000, 1),
    }


def _ms(plan: str, label: str) -> float | None:
    m = re.search(rf"{label}: ([\d.]+) ms", plan)
    return float(m.group(1)) if m else None


@mcp.tool()
@surfaced
def explain_analyze(fork_id: str, sql: str) -> dict:
    """EXPLAIN (ANALYZE, BUFFERS) a statement on a fork. It really executes the
    statement (on the fork). Returns the plan text plus planning/execution ms."""
    fork = _use(fork_id)
    with _connect(fork.url) as conn, conn.cursor() as cur:
        cur.execute(f"EXPLAIN (ANALYZE, BUFFERS) {sql}")
        plan = "\n".join(next(iter(r.values())) for r in cur.fetchall())
    return {"plan": plan, "planning_ms": _ms(plan, "Planning Time"),
            "execution_ms": _ms(plan, "Execution Time")}


@mcp.tool()
@surfaced
def schema_diff(fork_id: str) -> dict:
    """Schema and data changes made on the fork so far, compared to main."""
    _use(fork_id)
    return keon.sandbox_diff(fork_id)


@mcp.tool()
@surfaced
def destroy_fork(fork_id: str) -> dict:
    """Delete a fork now (otherwise it expires on its own)."""
    registry.reap()
    registry.destroy(fork_id)
    return {"destroyed": fork_id}


@mcp.tool()
@surfaced
def list_forks() -> dict:
    """Forks created by this server that are still alive."""
    registry.reap()
    return {"forks": [f.public() for f in registry.list()]}


def main() -> None:
    atexit.register(registry.destroy_all)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        mcp.run()  # stdio
    finally:
        registry.destroy_all()


if __name__ == "__main__":
    main()
