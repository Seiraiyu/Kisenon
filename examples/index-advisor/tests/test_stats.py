from unittest.mock import MagicMock

import psycopg

import index_advisor.stats as st


def _cur(one=None, rows=None):
    c = MagicMock()
    c.fetchone.return_value = one
    c.fetchall.return_value = rows or []
    return c


def test_check_pgss_missing_extension():
    conn = MagicMock()
    conn.execute.side_effect = [_cur(one=None)]
    msg = st.check_pgss(conn)
    assert "not installed" in msg and "CREATE EXTENSION IF NOT EXISTS pg_stat_statements" in msg


def test_check_pgss_installed_but_unreadable():
    conn = MagicMock()
    conn.execute.side_effect = [
        _cur(one=(1,)),
        psycopg.errors.ObjectNotInPrerequisiteState(
            "pg_stat_statements must be loaded via shared_preload_libraries"),
    ]
    msg = st.check_pgss(conn)
    assert "shared_preload_libraries" in msg


def test_check_pgss_ok():
    conn = MagicMock()
    conn.execute.side_effect = [_cur(one=(1,)), _cur(rows=[(1,)])]
    assert st.check_pgss(conn) is None


def test_top_queries_maps_rows_and_passes_filters():
    conn = MagicMock()
    conn.execute.return_value = _cur(
        rows=[("123", "SELECT … WHERE customer_id = $1", 50, 4200.0, 84.0)])
    tops = st.top_queries(conn, match="%index_advisor.%", limit=5)
    assert tops == [st.TopQuery("123", "SELECT … WHERE customer_id = $1", 50, 4200.0, 84.0)]
    assert conn.execute.call_args.args[1] == ("%index_advisor.%", 5)


def test_table_stats_and_describe():
    conn = MagicMock()
    conn.execute.side_effect = [
        _cur(rows=[("orders", 1000000, 1000000)]),
        _cur(rows=[("orders",
                    "CREATE UNIQUE INDEX orders_pkey ON index_advisor.orders USING btree (id)")]),
        _cur(rows=[("orders", "id", "bigint"), ("orders", "customer_id", "integer")]),
    ]
    stats = st.table_stats(conn)
    assert stats["orders"].writes == 1000000 and len(stats["orders"].indexes) == 1
    text = st.describe_schema(conn, stats)
    assert "index_advisor.orders(id bigint, customer_id integer)" in text
    assert "~1000000 rows" in text and "orders_pkey" in text


def test_connect_retries_and_sets_search_path(monkeypatch):
    attempts = []
    good = MagicMock()

    def fake_connect(url, autocommit):
        attempts.append(url)
        if len(attempts) < 2:
            raise psycopg.OperationalError("endpoint not found")
        return good
    monkeypatch.setattr(psycopg, "connect", fake_connect)
    monkeypatch.setattr(st.time, "sleep", lambda s: None)
    assert st.connect("postgresql://f") is good
    good.execute.assert_any_call("SET search_path TO index_advisor, public")
