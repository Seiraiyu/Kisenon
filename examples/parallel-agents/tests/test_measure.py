import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import psycopg

import parallel_agents.measure as m


def _conn_returning(*results):
    """conn.execute(...) returns objects whose fetchone/fetchall yield `results` in order."""
    conn = MagicMock()
    cursors = []
    for r in results:
        cur = MagicMock()
        cur.fetchone.return_value = r
        cur.fetchall.return_value = r
        cursors.append(cur)
    conn.execute.side_effect = cursors
    return conn


def test_time_query_discards_warmup_and_takes_median():
    plans = [(json.dumps([{"Execution Time": t}]),) for t in (100.0, 9.0, 1.0, 5.0, 3.0, 7.0)]
    conn = _conn_returning(*plans)
    assert m.time_query(conn, "SELECT 1") == 5.0
    assert conn.execute.call_args_list[0].args[0] == "EXPLAIN (ANALYZE, FORMAT JSON) SELECT 1"


def test_time_query_accepts_already_parsed_json():
    conn = _conn_returning(*[([{"Execution Time": 2.0}],)] * 6)
    assert m.time_query(conn, "SELECT 1") == 2.0


def test_rows_of_normalizes_types():
    ts = datetime(2026, 6, 1, tzinfo=UTC)
    conn = _conn_returning([(ts, "view", Decimal("3")), (ts, "view", Decimal("3"))])
    rows = m.rows_of(conn, "SELECT ...")
    assert rows == {(ts.isoformat(), "view", 3): 2}


def test_describe_schema_lists_columns_and_indexes():
    conn = _conn_returning(
        [("events", "id", "bigint"), ("events", "kind", "text")],
        [("CREATE UNIQUE INDEX events_pkey ON parallel_agents.events USING btree (id)",)],
    )
    text = m.describe_schema(conn)
    assert "events(id bigint, kind text)" in text
    assert "events_pkey" in text


def test_connect_retries_then_sets_search_path(monkeypatch):
    attempts = []
    good = MagicMock()

    def fake_connect(url, autocommit):
        attempts.append(url)
        if len(attempts) < 2:
            raise psycopg.OperationalError("endpoint not found")
        return good
    monkeypatch.setattr(psycopg, "connect", fake_connect)
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    assert m.connect("postgresql://f") is good
    good.execute.assert_any_call("SET search_path TO parallel_agents")
