"""Benchmark each proposed index on its own fork, then rank."""
from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass
from typing import Any

from index_advisor.keon import forked
from index_advisor.llm import LLMError
from index_advisor.output import event
from index_advisor.stats import TableStats, connect

SYSTEM = """You are a PostgreSQL 17 indexing expert. Propose at most {n} indexes (B-tree or
expression) that would speed up the slow statements below. Each candidate is benchmarked
on its own disposable fork, so be concrete.
Reply with only a ```json block:
{{"candidates": [{{"queryid": "<queryid it targets>", "table": "<schema.table>",
  "index_sql": "CREATE INDEX ...", "sample_query": "<that statement with realistic literal
  values in place of $1, $2, ...>", "why": "<one sentence>"}}]}}
Schema-qualify table names. Don't propose an index that already exists."""

USER = """Tables:
{schema}

Top statements by total execution time (pg_stat_statements):
{tops}"""

_CREATE_INDEX = re.compile(r"^\s*CREATE\s+(UNIQUE\s+)?INDEX\b", re.I)
_READ = re.compile(r"^\s*(SELECT|WITH)\b", re.I)


@dataclass(slots=True)
class Proposal:
    queryid: str
    table: str
    index_sql: str
    sample_query: str
    why: str


@dataclass(slots=True)
class Result:
    proposal: Proposal
    branch: str
    before_ms: float | None = None
    after_ms: float | None = None
    index_bytes: int = 0
    used: bool = False
    calls: int = 0
    est_saved_ms: float = 0.0
    write_note: str = ""
    error: str | None = None


def parse_proposals(data: Any, *, max_n: int) -> list[Proposal]:
    items = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LLMError('expected {"candidates": [...]} from the model')
    out: list[Proposal] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        idx = str(it.get("index_sql", "")).strip().rstrip(";").strip()
        q = str(it.get("sample_query", "")).strip().rstrip(";").strip()
        if not _CREATE_INDEX.match(idx) or not _READ.match(q):
            event("proposal skipped", index_sql=idx[:80], reason="need CREATE INDEX + SELECT")
            continue
        out.append(Proposal(str(it.get("queryid", "")), str(it.get("table", "")), idx, q,
                            str(it.get("why", ""))))
    return out[:max_n]


def to_concurrent(index_sql: str) -> str:
    return re.sub(
        r"^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+(?!CONCURRENTLY\b)",
        lambda m: f"CREATE {'UNIQUE ' if m.group(1) else ''}INDEX CONCURRENTLY ",
        index_sql, count=1, flags=re.I,
    )


def without_concurrently(index_sql: str) -> str:
    """On a private fork a plain build is faster; CONCURRENTLY is for main."""
    return re.sub(r"\bCONCURRENTLY\s+", "", index_sql, count=1, flags=re.I)


def time_query(conn: Any, query: str, runs: int = 3) -> tuple[float, Any]:
    """Median EXPLAIN ANALYZE time (ms) after one warm-up, plus the last JSON plan."""
    times: list[float] = []
    plan: Any = None
    for _ in range(runs + 1):
        (plan,) = conn.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {query}").fetchone()
        if isinstance(plan, str):
            plan = json.loads(plan)
        times.append(float(plan[0]["Execution Time"]))
    return statistics.median(times[1:]), plan


def index_names(conn: Any, table: str) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT indexrelid::regclass::text FROM pg_index WHERE indrelid = %s::regclass", (table,)
    ).fetchall()}


def benchmark(
    p: Proposal, *, project: str, name: str, keep: bool, stats: dict[str, TableStats], calls: int,
) -> Result:
    r = Result(proposal=p, branch=name, calls=calls)
    try:
        with forked(project=project, name=name, keep=keep) as (branch, url):
            event("branch forked", id=branch.id, index=p.index_sql[:80],
                  duration_ms=branch.created_in_ms)
            conn = connect(url)
            try:
                r.before_ms, _ = time_query(conn, p.sample_query)
                before = index_names(conn, p.table)
                conn.execute(without_concurrently(p.index_sql))
                new = index_names(conn, p.table) - before
                r.after_ms, plan = time_query(conn, p.sample_query)
                plan_text = json.dumps(plan)
                r.used = any(n.split(".")[-1] in plan_text for n in new)
                r.index_bytes = sum(int(conn.execute(
                    "SELECT pg_relation_size(%s::regclass)", (n,)).fetchone()[0]) for n in new)
            finally:
                conn.close()
        event("measured", index=p.index_sql[:80], before_ms=round(r.before_ms, 2),
              after_ms=round(r.after_ms, 2), used=r.used)
    except Exception as e:  # noqa: BLE001 — one bad candidate must not stop the rest
        r.error = f"{type(e).__name__}: {e}"
        event("candidate failed", index=p.index_sql[:80], error=r.error[:200])
    ts = stats.get(p.table.split(".")[-1])
    r.write_note = (
        f"{ts.writes} writes since stats reset; each would maintain "
        f"{len(ts.indexes) + 1} indexes (was {len(ts.indexes)})" if ts else "table stats unknown"
    )
    if r.error is None and r.used and r.before_ms is not None and r.after_ms is not None:
        r.est_saved_ms = max(0.0, r.before_ms - r.after_ms) * calls
    return r


def rank(results: list[Result]) -> list[Result]:
    return sorted(results, key=lambda r: r.est_saved_ms, reverse=True)
