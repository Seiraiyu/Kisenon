import pytest

from rag_complex.store import IndexMismatch, ensure_schema, vec, vector_search


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, meta=None, rows=None):
        self.meta, self.rows, self.sqls = meta or [], rows or [], []

    def execute(self, sql, params=None):
        self.sqls.append(" ".join(sql.split()))
        if sql.startswith("SELECT key, value FROM rag_complex.meta"):
            return FakeCursor(self.meta)
        return FakeCursor(self.rows)


def test_vec_literal():
    assert vec([1.0, 0.25]) == "[1,0.25]"


def test_ensure_schema_builds_tables_with_dim():
    conn = FakeConn()
    ensure_schema(conn, "fastembed", 384, "block", reset=False)
    assert any("embedding vector(384) NOT NULL" in s for s in conn.sqls)
    assert any("USING hnsw (embedding vector_cosine_ops)" in s for s in conn.sqls)
    assert not any(s.startswith("DROP") for s in conn.sqls)


def test_ensure_schema_refuses_other_embedder_without_reset():
    conn = FakeConn(meta=[("embedder", "voyage"), ("dim", "1024")])
    with pytest.raises(IndexMismatch, match="--reset"):
        ensure_schema(conn, "fastembed", 384, "block", reset=False)


def test_vector_search_maps_rows_to_hits():
    conn = FakeConn(rows=[("doc1", 3, "2204.00498", "text", "A > B", 2, 2)])
    hits = vector_search(conn, [0.5], 20)
    assert hits == [{"id": "doc1-3", "document_id": "doc1", "ord": 3, "source": "2204.00498",
                     "text": "text", "heading_context": "A > B", "page_start": 2, "page_end": 2}]
    assert "LIMIT %s" in conn.sqls[0]
