"""Read-only schema introspection against the project's main branch.

The agent's `inspect_schema` tool runs here against KISENON_URL. The connection
is read-only and we reject anything that isn't a single SELECT/WITH, so the
agent can look at production but can never write to it — every write goes
through a scoped sandbox.
"""
from __future__ import annotations

import re
from typing import Any

_READONLY_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


class NotReadOnly(ValueError):
    """The agent tried to run a non-SELECT statement against main."""


def guard_select(sql: str) -> None:
    body = sql.strip().rstrip(";")
    if ";" in body:
        raise NotReadOnly("inspect_schema runs one statement only")
    if not _READONLY_RE.match(body):
        raise NotReadOnly("inspect_schema only runs SELECT/WITH queries")


def open_readonly(url: str):  # pragma: no cover — exercised live
    import psycopg
    conn = psycopg.connect(url, autocommit=True)
    conn.read_only = True
    return conn


def run_select(conn, sql: str, *, row_cap: int = 200) -> list[dict[str, Any]]:
    guard_select(sql)
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description] if cur.description else []
        rows = cur.fetchmany(row_cap)
        return [dict(zip(cols, r)) for r in rows]


def summarize(conn) -> str:  # pragma: no cover — exercised live
    """A compact text schema dump for the system prompt."""
    rows = run_select(
        conn,
        "SELECT table_name, column_name, data_type, character_maximum_length "
        "FROM information_schema.columns WHERE table_schema='public' "
        "ORDER BY table_name, ordinal_position",
        row_cap=2000,
    )
    by_table: dict[str, list[str]] = {}
    for r in rows:
        col = f"{r['column_name']} {r['data_type']}"
        if r["character_maximum_length"]:
            col += f"({r['character_maximum_length']})"
        by_table.setdefault(r["table_name"], []).append(col)
    return "\n".join(f"{t}({', '.join(cols)})" for t, cols in by_table.items())
