"""Run cases against the fork: ask the model, execute, score, reset after writes."""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from text2sql_eval.cases import Case, Outcome, score
from text2sql_eval.output import event

SCHEMA = "text2sql_eval"

SYSTEM_PROMPT = """You translate a question into ONE PostgreSQL 17 statement.
The tables below are on the search_path; do not schema-qualify them.
If the question asks to change data, write the DELETE/UPDATE/INSERT itself:
it runs on a disposable fork of the database, never on production.
Reply with only the SQL inside a ```sql fenced block.

Schema:
{schema}"""

_READ_TAGS = {"SELECT", "SHOW", "EXPLAIN", "VALUES", "TABLE"}
_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


@dataclass(slots=True)
class CaseResult:
    id: str
    question: str
    sql: str
    executed: bool
    match: str | None
    reason: str
    reset: bool
    duration_ms: int


def connect(url: str, attempts: int = 10, delay_s: float = 2.0) -> Any:
    """Open an autocommit connection, retrying while a (re)started compute warms up."""
    import psycopg
    for i in range(attempts):
        try:
            conn = psycopg.connect(url, autocommit=True)
            break
        except psycopg.OperationalError:
            if i == attempts - 1:
                raise
            time.sleep(delay_s)
    conn.execute(f"SET search_path TO {SCHEMA}")
    conn.execute("SET statement_timeout = '30s'")
    return conn


def describe_schema(conn: Any) -> str:
    rows = conn.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = %s ORDER BY table_name, ordinal_position",
        (SCHEMA,),
    ).fetchall()
    tables: dict[str, list[str]] = {}
    for table, column, dtype in rows:
        tables.setdefault(table, []).append(f"{column} {dtype}")
    return "\n".join(f"{t}({', '.join(cols)})" for t, cols in tables.items())


def extract_sql(text: str) -> str:
    m = _FENCE.search(text)
    return (m.group(1) if m else text).strip().rstrip(";").strip()


def execute(conn: Any, sql: str) -> Outcome:
    started = time.monotonic()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall() if cur.description else None
            status, rowcount = cur.statusmessage or "", cur.rowcount
    except Exception as e:  # noqa: BLE001 — a failing statement is a graded outcome
        return Outcome(sql, None, None, "", f"{type(e).__name__}: {e}", _ms(started))
    return Outcome(sql, rows, rowcount, status, None, _ms(started))


def mutated(o: Outcome) -> bool:
    """True if the statement may have changed the fork (so it must be reset)."""
    return o.error is None and o.status.split(" ", 1)[0].upper() not in _READ_TAGS


def run_eval(
    cases: list[Case],
    *,
    ask: Callable[[str, str], str],
    connect: Callable[[], Any],
    reset_fork: Callable[[], None],
) -> list[CaseResult]:
    conn = connect()
    results: list[CaseResult] = []
    try:
        schema = describe_schema(conn)
        for case in cases:
            sql = extract_sql(ask(case.question, schema))
            event("case", id=case.id, sql=sql.replace("\n", " ")[:120])
            o = execute(conn, sql)
            match, reason = score(case, o)
            did_reset = mutated(o)
            if did_reset:
                conn.close()
                reset_fork()
                conn = connect()
            event("case done", id=case.id, match=match, reason=reason, reset=did_reset)
            results.append(CaseResult(
                id=case.id, question=case.question, sql=sql, executed=o.error is None,
                match=match, reason=reason, reset=did_reset, duration_ms=o.duration_ms,
            ))
    finally:
        conn.close()
    return results


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
