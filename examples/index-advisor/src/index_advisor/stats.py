"""Read-only statistics from main: pg_stat_statements + table/index stats."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "index_advisor"

PGSS_MISSING = (
    "pg_stat_statements is not installed in this database. Create it on main:\n"
    "  psql \"$KISENON_URL\" -c 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements'\n"
    "If that fails, the extension isn't available on your Kisenon plan/region "
    "(see README#troubleshooting)."
)

TOP_SQL = """
SELECT queryid::text, query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND query ILIKE %s
  AND (query ILIKE 'select%%' OR query ILIKE 'with%%')
  AND query NOT ILIKE '%%pg_stat_statements%%'
ORDER BY total_exec_time DESC
LIMIT %s
"""


@dataclass(slots=True)
class TopQuery:
    queryid: str
    query: str
    calls: int
    total_ms: float
    mean_ms: float


@dataclass(slots=True)
class TableStats:
    name: str
    rows: int
    writes: int  # n_tup_ins + n_tup_upd + n_tup_del since stats reset
    indexes: list[str] = field(default_factory=list)


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


def check_pgss(conn: Any) -> str | None:
    """None if pg_stat_statements is usable, else a message saying how to fix it."""
    if conn.execute(
        "SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'"
    ).fetchone() is None:
        return PGSS_MISSING
    try:
        conn.execute("SELECT 1 FROM pg_stat_statements LIMIT 1").fetchall()
    except Exception as e:  # noqa: BLE001 — any failure here means "not usable"
        return (
            f"pg_stat_statements is installed but can't be read ({type(e).__name__}: {e}). "
            "It must be in shared_preload_libraries on the compute; see README#troubleshooting."
        )
    return None


def top_queries(conn: Any, *, match: str, limit: int) -> list[TopQuery]:
    return [TopQuery(str(r[0]), r[1], int(r[2]), float(r[3]), float(r[4]))
            for r in conn.execute(TOP_SQL, (match, limit)).fetchall()]


def table_stats(conn: Any) -> dict[str, TableStats]:
    out = {
        name: TableStats(name, int(rows), int(writes))
        for name, rows, writes in conn.execute(
            "SELECT relname, n_live_tup, n_tup_ins + n_tup_upd + n_tup_del "
            "FROM pg_stat_user_tables WHERE schemaname = %s", (SCHEMA,)
        ).fetchall()
    }
    for table, indexdef in conn.execute(
        "SELECT tablename, indexdef FROM pg_indexes WHERE schemaname = %s ORDER BY indexname",
        (SCHEMA,),
    ).fetchall():
        if table in out:
            out[table].indexes.append(indexdef)
    return out


def describe_schema(conn: Any, stats: dict[str, TableStats]) -> str:
    cols: dict[str, list[str]] = {}
    for table, column, dtype in conn.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (SCHEMA,)
    ).fetchall():
        cols.setdefault(table, []).append(f"{column} {dtype}")
    lines = []
    for table, c in cols.items():
        s = stats.get(table)
        lines.append(f"{SCHEMA}.{table}({', '.join(c)})")
        if s:
            lines.append(f"  ~{s.rows} rows; indexes: " + ("; ".join(s.indexes) or "none"))
    return "\n".join(lines)
