from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from agent_memory import store

NOW = datetime(2026, 9, 24, tzinfo=UTC)


def test_rank_prefers_recent_at_equal_similarity():
    rows = [
        (1, "old", 0.8, NOW - timedelta(days=60)),
        (2, "new", 0.8, NOW),
    ]
    facts = store.rank(rows, k=2, now=NOW)
    assert [f.content for f in facts] == ["new", "old"]
    assert facts[0].recency == 1.0
    assert facts[1].recency == pytest.approx(0.25)  # two half-lives of 30 days


def test_rank_high_similarity_beats_slightly_newer():
    rows = [
        (1, "relevant", 0.9, NOW - timedelta(days=5)),
        (2, "fresh but off-topic", 0.3, NOW),
    ]
    assert store.rank(rows, k=1, now=NOW)[0].content == "relevant"


def test_rank_truncates_to_k():
    rows = [(i, str(i), 0.5, NOW) for i in range(10)]
    assert len(store.rank(rows, k=3, now=NOW)) == 3


def test_upsert_merges_near_duplicate():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (7, 0.95)
    assert store.upsert_fact(conn, "User is vegetarian", [0.1], 1) == "merged"
    update_sql = conn.execute.call_args_list[-1].args[0]
    assert update_sql.startswith("UPDATE agent_memory.facts SET hits = hits + 1")


def test_upsert_inserts_new_fact():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = (7, 0.42)
    assert store.upsert_fact(conn, "User lives in Lisbon", [0.1], 1) == "added"
    assert conn.execute.call_args_list[-1].args[0].startswith("INSERT INTO agent_memory.facts")


def test_upsert_inserts_when_table_empty():
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    assert store.upsert_fact(conn, "first", [0.1], 1) == "added"


def test_ensure_schema_rejects_dim_mismatch(monkeypatch):
    monkeypatch.setattr(store, "register_vector", lambda conn: None)
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = ("1024",)
    with pytest.raises(store.DimMismatch, match="--reset"):
        store.ensure_schema(conn, 384)


def test_ensure_schema_records_dim_on_first_run(monkeypatch):
    monkeypatch.setattr(store, "register_vector", lambda conn: None)
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = None
    store.ensure_schema(conn, 384)
    sqls = [c.args[0] for c in conn.execute.call_args_list]
    assert "vector(384)" in sqls[0]
    assert any(s.startswith("INSERT INTO agent_memory.meta") for s in sqls)


def test_ensure_schema_reset_drops_first(monkeypatch):
    monkeypatch.setattr(store, "register_vector", lambda conn: None)
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = ("384",)
    store.ensure_schema(conn, 384, reset=True)
    assert conn.execute.call_args_list[0].args[0] == "DROP SCHEMA IF EXISTS agent_memory CASCADE"
