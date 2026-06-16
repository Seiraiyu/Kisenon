"""SQL execution against the forked branch, with row-cap + error capture.

The single tool exposed to the LLM is `run_sql(sql)`. We reject multi-statement
input so the tool-call log stays one statement per entry — easier for humans to
read and easier for the agent to reason about.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any


class MultiStatementError(ValueError):
    """Caller passed more than one SQL statement in a single `run_sql` call."""


@dataclass(slots=True)
class RunSqlResult:
    sql: str
    rows_returned: int
    rows_truncated: bool
    duration_ms: int
    result_preview: list[Any]
    error: str | None


_MULTI_STMT_RE = re.compile(r";\s*\S")


def reject_multi_statement(sql: str) -> None:
    if _MULTI_STMT_RE.search(sql):
        raise MultiStatementError(
            "`run_sql` accepts a single SQL statement. Split into multiple tool calls."
        )


def run_sql(connection: Any, sql: str, *, row_cap: int = 1000) -> RunSqlResult:
    """Execute one SQL statement against the open psycopg connection.

    Returns a RunSqlResult. DB errors are captured (not raised) so the agent
    loop can return them to the model and let it react.
    """
    reject_multi_statement(sql)
    started = time.monotonic()
    try:
        with connection.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                rows_returned = cur.rowcount or 0
                preview: list[Any] = []
                truncated = False
            else:
                rows = cur.fetchall()
                rows_returned = len(rows)
                columns = [d[0] for d in cur.description]
                truncated = rows_returned > row_cap
                kept = rows[:row_cap]
                preview = [dict(zip(columns, r, strict=False)) for r in kept]
    except MultiStatementError:
        raise
    except Exception as e:  # noqa: BLE001 — surface any DB error to the agent
        duration_ms = int((time.monotonic() - started) * 1000)
        return RunSqlResult(
            sql=sql,
            rows_returned=0,
            rows_truncated=False,
            duration_ms=duration_ms,
            result_preview=[],
            error=f"{type(e).__name__}: {e}",
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    return RunSqlResult(
        sql=sql,
        rows_returned=rows_returned,
        rows_truncated=truncated,
        duration_ms=duration_ms,
        result_preview=preview,
        error=None,
    )
