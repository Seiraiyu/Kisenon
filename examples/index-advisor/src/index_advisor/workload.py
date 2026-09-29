"""A small, deterministic read workload so pg_stat_statements has something to rank.

Runs on MAIN (reads only). Parameters are sent server-side, so pg_stat_statements
groups each query shape under one queryid with $1-style placeholders.
"""
from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

SINCE = datetime(2026, 6, 1, tzinfo=UTC)

QUERIES: list[tuple[str, Callable[[random.Random], tuple]]] = [
    (
        "SELECT id, total_cents, created_at FROM index_advisor.orders "
        "WHERE customer_id = %s ORDER BY created_at DESC LIMIT 20",
        lambda r: (r.randint(1, 100000),),
    ),
    (
        "SELECT count(*) FROM index_advisor.orders WHERE status = %s AND created_at >= %s",
        lambda r: (r.choice(["pending", "refunded"]), SINCE),
    ),
    (
        "SELECT id, region FROM index_advisor.customers WHERE lower(email) = %s",
        lambda r: (f"customer{r.randint(1, 100000)}@example.com",),
    ),
]


def run_workload(conn: Any, *, rounds: int, seed: int = 0) -> int:
    rng = random.Random(seed)
    n = 0
    for _ in range(rounds):
        for sql, params in QUERIES:
            conn.execute(sql, params(rng)).fetchall()
            n += 1
    return n
