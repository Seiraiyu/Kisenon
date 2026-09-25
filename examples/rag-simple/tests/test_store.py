import pytest

from rag_simple.store import DimensionMismatch, ensure_schema, replace_source, search, vec


class FakeCursor:
    def __init__(self, one=None, rows=None):
        self._one, self._rows = one, rows or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, stored_dim="384", rows=None):
        self.calls: list[tuple[str, tuple | None]] = []
        self.stored_dim, self.rows = stored_dim, rows or []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))
        if "SELECT value FROM rag_simple.meta" in sql:
            return FakeCursor(one=(self.stored_dim,))
        return FakeCursor(rows=self.rows)


def test_vec_literal():
    assert vec([0.5, -1.0, 2.0]) == "[0.5,-1,2]"


def test_ensure_schema_creates_vector_table_with_dim_and_hnsw_index():
    conn = FakeConn()
    ensure_schema(conn, 384)
    sqls = [s for s, _ in conn.calls]
    assert sqls[0] == "CREATE EXTENSION IF NOT EXISTS vector"
    assert any("embedding vector(384) NOT NULL" in s for s in sqls)
    assert any("USING hnsw (embedding vector_cosine_ops)" in s for s in sqls)
    assert not any(s.startswith("DROP") for s in sqls)


def test_ensure_schema_reset_drops_first():
    conn = FakeConn()
    ensure_schema(conn, 384, reset=True)
    assert any(s.startswith("DROP TABLE IF EXISTS rag_simple.chunks") for s, _ in conn.calls)


def test_ensure_schema_raises_on_dimension_mismatch():
    with pytest.raises(DimensionMismatch, match="--reset"):
        ensure_schema(FakeConn(stored_dim="1024"), 384)


def test_replace_source_deletes_then_inserts_in_order():
    conn = FakeConn()
    replace_source(conn, "a.md", ["one", "two"], [[1.0], [2.0]])
    assert conn.calls[0] == ("DELETE FROM rag_simple.chunks WHERE source = %s", ("a.md",))
    assert conn.calls[1][1] == ("a.md", 0, "one", "[1]")
    assert conn.calls[2][1] == ("a.md", 1, "two", "[2]")


def test_search_orders_by_cosine_distance_with_limit():
    conn = FakeConn(rows=[("a.md", 0, "hi", 0.91234)])
    hits = search(conn, [0.1, 0.2], k=5)
    sql, params = conn.calls[0]
    assert "ORDER BY embedding <=> %s::vector LIMIT %s" in sql
    assert params == ("[0.1,0.2]", "[0.1,0.2]", 5)
    assert hits == [{"source": "a.md", "ord": 0, "text": "hi", "score": 0.9123}]
