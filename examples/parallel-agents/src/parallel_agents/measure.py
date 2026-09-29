"""Fork-side measurement: connect, describe schema, fetch rows, time queries."""
from __future__ import annotations

import json
import statistics
import time
from collections import Counter
from decimal import Decimal
from typing import Any

SCHEMA = "parallel_agents"


def connect(url: str, attempts: int = 10, delay_s: float = 2.0) -> Any:
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
    conn.execute("SET statement_timeout = '120s'")
    return conn


def describe_schema(conn: Any) -> str:
    cols = conn.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = %s ORDER BY table_name, ordinal_position",
        (SCHEMA,),
    ).fetchall()
    idx = conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE schemaname = %s ORDER BY indexname", (SCHEMA,)
    ).fetchall()
    tables: dict[str, list[str]] = {}
    for table, column, dtype in cols:
        tables.setdefault(table, []).append(f"{column} {dtype}")
    lines = [f"{t}({', '.join(c)})" for t, c in tables.items()]
    return "\n".join(lines + ["Indexes:"] + [f"  {d}" for (d,) in idx])


def _norm(v: Any) -> Any:
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def rows_of(conn: Any, query: str) -> Counter:
    """Result set as a multiset of normalized tuples (order-insensitive compare)."""
    return Counter(tuple(_norm(v) for v in r) for r in conn.execute(query).fetchall())


def time_query(conn: Any, query: str, runs: int = 5) -> float:
    """Median EXPLAIN ANALYZE execution time (ms); the first run warms caches."""
    times: list[float] = []
    for _ in range(runs + 1):
        (plan,) = conn.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {query}").fetchone()
        if isinstance(plan, str):
            plan = json.loads(plan)
        times.append(float(plan[0]["Execution Time"]))
    return statistics.median(times[1:])


def explain_text(conn: Any, query: str) -> str:
    return "\n".join(r[0] for r in conn.execute(f"EXPLAIN (ANALYZE, BUFFERS) {query}").fetchall())
