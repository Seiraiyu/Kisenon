import json
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

import index_advisor.bench as bench
from index_advisor.bench import (
    Proposal,
    Result,
    parse_proposals,
    rank,
    to_concurrent,
    without_concurrently,
)
from index_advisor.keon import Branch
from index_advisor.llm import LLMError
from index_advisor.stats import TableStats

GOOD = {"queryid": "1", "table": "index_advisor.orders",
        "index_sql": "CREATE INDEX ON index_advisor.orders (customer_id, created_at DESC);",
        "sample_query": "SELECT id FROM index_advisor.orders WHERE customer_id = 42", "why": "w"}


def test_parse_proposals_validates_and_caps():
    bad_sql = dict(GOOD, index_sql="DROP TABLE orders")
    bad_q = dict(GOOD, sample_query="DELETE FROM orders")
    out = parse_proposals({"candidates": [GOOD, bad_sql, bad_q, GOOD, GOOD]}, max_n=2)
    assert len(out) == 2
    assert out[0].index_sql == "CREATE INDEX ON index_advisor.orders (customer_id, created_at DESC)"


def test_parse_proposals_rejects_wrong_shape():
    with pytest.raises(LLMError, match="candidates"):
        parse_proposals([GOOD], max_n=5)


@pytest.mark.parametrize("src, want", [
    ("CREATE INDEX ON t (a)", "CREATE INDEX CONCURRENTLY ON t (a)"),
    ("create unique index i ON t (a)", "CREATE UNIQUE INDEX CONCURRENTLY i ON t (a)"),
    ("CREATE INDEX CONCURRENTLY ON t (a)", "CREATE INDEX CONCURRENTLY ON t (a)"),
])
def test_to_concurrent(src, want):
    assert to_concurrent(src) == want


def test_without_concurrently():
    assert without_concurrently("CREATE INDEX CONCURRENTLY i ON t (a)") == "CREATE INDEX i ON t (a)"


def test_time_query_median_and_last_plan():
    conn = MagicMock()
    plans = [[{"Execution Time": t, "Plan": {"Index Name": "x"}}] for t in (50.0, 3.0, 1.0, 2.0)]
    conn.execute.return_value.fetchone.side_effect = [(json.dumps(p),) for p in plans]
    ms, plan = bench.time_query(conn, "SELECT 1")
    assert ms == 2.0 and plan[0]["Plan"]["Index Name"] == "x"


def _patch_fork(monkeypatch, *, plan_mentions="orders_customer_id_created_at_idx"):
    @contextmanager
    def fake_forked(project, name, keep):
        yield Branch(name=name, id="br"), "postgresql://fork"
    monkeypatch.setattr(bench, "forked", fake_forked)
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (8192 * 100,)
    monkeypatch.setattr(bench, "connect", lambda url: conn)
    names = iter([{"orders_pkey"}, {"orders_pkey", "orders_customer_id_created_at_idx"}])
    monkeypatch.setattr(bench, "index_names", lambda c, t: next(names))
    times = iter([(80.0, []), (0.5, [{"Plan": {"Index Name": plan_mentions}}])])
    monkeypatch.setattr(bench, "time_query", lambda c, q: next(times))
    return conn


STATS = {"orders": TableStats("orders", 1000000, 1000000, ["CREATE UNIQUE INDEX orders_pkey …"])}


def test_benchmark_measures_on_fork(monkeypatch):
    conn = _patch_fork(monkeypatch)
    p = Proposal(**GOOD)
    r = bench.benchmark(p, project="pr", name="index-advisor-x-1", keep=False, stats=STATS, calls=50)
    assert r.error is None
    assert (r.before_ms, r.after_ms, r.used, r.index_bytes) == (80.0, 0.5, True, 819200)
    assert r.est_saved_ms == pytest.approx((80.0 - 0.5) * 50)
    assert "1000000 writes" in r.write_note and "2 indexes (was 1)" in r.write_note
    conn.execute.assert_any_call(p.index_sql)


def test_benchmark_unused_index_saves_nothing(monkeypatch):
    _patch_fork(monkeypatch, plan_mentions="orders_pkey")
    r = bench.benchmark(Proposal(**GOOD), project="pr", name="n", keep=False, stats=STATS, calls=50)
    assert r.used is False and r.est_saved_ms == 0.0


def test_benchmark_captures_errors(monkeypatch):
    @contextmanager
    def broken(project, name, keep):
        raise RuntimeError("fork failed")
        yield
    monkeypatch.setattr(bench, "forked", broken)
    r = bench.benchmark(Proposal(**GOOD), project="pr", name="n", keep=False, stats=STATS, calls=1)
    assert r.error == "RuntimeError: fork failed" and r.est_saved_ms == 0.0


def test_rank_orders_by_estimated_savings():
    p = Proposal(**GOOD)
    a = Result(p, "a", est_saved_ms=10.0)
    b = Result(p, "b", est_saved_ms=500.0)
    c = Result(p, "c", est_saved_ms=0.0)
    assert [r.branch for r in rank([a, b, c])] == ["b", "a", "c"]
