"""The race: one agent (single LLM call) per strategy, each on its own fork."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from parallel_agents.keon import Branch, create_branch, find_branch_id, get_branch_url
from parallel_agents.llm import extract_json
from parallel_agents.measure import connect, describe_schema, explain_text, rows_of, time_query
from parallel_agents.output import event

STRATEGIES = {
    "index": "Add index(es) only. Keep the query text exactly as given.",
    "rewrite": "Rewrite the query only. No DDL: setup_sql must be an empty list.",
    "matview": "Create a materialized view that precomputes the answer, and query it instead.",
}

SYSTEM = """You are a PostgreSQL 17 performance engineer working on a disposable fork.
You must use this strategy: {strategy}
Tables are on the search_path; do not schema-qualify them.
Reply with only a ```json block:
{{"setup_sql": ["<one statement>", ...], "query": "<the query to run>", "rationale": "<one sentence>"}}
The query you return must produce exactly the same rows as the original."""

USER = """Goal: make this query run in under {goal_ms} ms. It currently takes {baseline_ms:.1f} ms.

Schema:
{schema}

Query:
{query}

Current plan:
{plan}"""

Ask = Callable[[str, str], str]  # (system, user) -> model text


@dataclass(slots=True)
class Candidate:
    strategy: str
    branch: Branch | None = None
    setup_sql: list[str] = field(default_factory=list)
    query: str = ""
    rationale: str = ""
    baseline_ms: float | None = None
    after_ms: float | None = None
    correct: bool = False
    error: str | None = None


def run_candidate(
    strategy: str, *, project: str, name: str, query: str, goal_ms: float, ask: Ask,
    created: list[Branch],
) -> Candidate:
    c = Candidate(strategy=strategy, query=query)
    conn = None
    try:
        parent = find_branch_id(project=project, name="main")
        c.branch = create_branch(project=project, name=name, parent_id=parent)
        created.append(c.branch)  # the caller deletes everything in `created`
        event("branch forked", id=c.branch.id, strategy=strategy, ms=c.branch.created_in_ms)
        conn = connect(get_branch_url(project=project, branch=c.branch.name))
        baseline = rows_of(conn, query)
        c.baseline_ms = time_query(conn, query)
        proposal = extract_json(ask(
            SYSTEM.format(strategy=STRATEGIES[strategy]),
            USER.format(goal_ms=goal_ms, baseline_ms=c.baseline_ms, schema=describe_schema(conn),
                        query=query, plan=explain_text(conn, query)),
        ))
        c.setup_sql = [str(s) for s in proposal.get("setup_sql") or []]
        c.query = str(proposal.get("query") or query).strip().rstrip(";")
        c.rationale = str(proposal.get("rationale") or "")
        for stmt in c.setup_sql:
            event("apply", strategy=strategy, sql=stmt.replace("\n", " ")[:120])
            conn.execute(stmt)
        c.correct = rows_of(conn, c.query) == baseline
        c.after_ms = time_query(conn, c.query)
        event("measured", strategy=strategy, before_ms=round(c.baseline_ms, 2),
              after_ms=round(c.after_ms, 2), correct=c.correct)
    except Exception as e:  # noqa: BLE001 — one agent failing must not sink the race
        c.error = f"{type(e).__name__}: {e}"
        event("agent failed", strategy=strategy, error=c.error[:200])
    finally:
        if conn is not None:
            conn.close()
    return c


async def race(
    strategies: list[str], *, project: str, run_id: str, query: str, goal_ms: float, ask: Ask,
    created: list[Branch],
) -> list[Candidate]:
    return list(await asyncio.gather(*(
        asyncio.to_thread(
            run_candidate, s, project=project, name=f"parallel-agents-{run_id}-{s}",
            query=query, goal_ms=goal_ms, ask=ask, created=created,
        )
        for s in strategies
    )))


def pick_winner(candidates: list[Candidate]) -> Candidate | None:
    ok = [c for c in candidates if c.error is None and c.correct and c.after_ms is not None]
    return min(ok, key=lambda c: c.after_ms) if ok else None
