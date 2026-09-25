"""Postgres side: `rag_complex` schema with documents, chunks (pgvector), meta."""
from __future__ import annotations

from typing import Any

from rag_complex.chunker import Chunk


class IndexMismatch(RuntimeError):
    """The tables were built with a different embedder (dimension)."""


def vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def read_meta(conn: Any) -> dict[str, str]:
    try:
        return dict(conn.execute("SELECT key, value FROM rag_complex.meta").fetchall())
    except Exception:  # noqa: BLE001 — schema not created yet
        return {}


def ensure_schema(conn: Any, embedder: str, dim: int, chunker: str, *, reset: bool) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("CREATE SCHEMA IF NOT EXISTS rag_complex")
    if reset:
        conn.execute("DROP TABLE IF EXISTS rag_complex.chunks, rag_complex.documents, "
                     "rag_complex.meta")
    conn.execute("CREATE TABLE IF NOT EXISTS rag_complex.meta "
                 "(key text PRIMARY KEY, value text NOT NULL)")
    meta = read_meta(conn)
    if meta and (meta.get("embedder"), meta.get("dim")) != (embedder, str(dim)):
        raise IndexMismatch(
            f"index was built with {meta.get('embedder')} (dim={meta.get('dim')}), "
            f"not {embedder} (dim={dim}). Re-ingest with --reset."
        )
    for key, value in (("embedder", embedder), ("dim", str(dim)), ("chunker", chunker)):
        conn.execute("INSERT INTO rag_complex.meta VALUES (%s, %s) "
                     "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))
    conn.execute("""CREATE TABLE IF NOT EXISTS rag_complex.documents (
        id     text PRIMARY KEY,
        source text NOT NULL UNIQUE,
        title  text NOT NULL,
        pages  int  NOT NULL)""")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS rag_complex.chunks (
        document_id     text NOT NULL REFERENCES rag_complex.documents(id) ON DELETE CASCADE,
        ord             int  NOT NULL,
        kind            text NOT NULL,
        text            text NOT NULL,
        heading_context text NOT NULL,
        page_start      int  NOT NULL,
        page_end        int  NOT NULL,
        embedding       vector({int(dim)}) NOT NULL,
        PRIMARY KEY (document_id, ord))""")
    conn.execute("CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw "
                 "ON rag_complex.chunks USING hnsw (embedding vector_cosine_ops)")


def replace_document(
    conn: Any, doc_id: str, source: str, title: str, pages: int,
    chunks: list[Chunk], vectors: list[list[float]],
) -> None:
    """Idempotent: delete the document (cascades to its chunks), then insert fresh."""
    with conn.transaction():
        conn.execute("DELETE FROM rag_complex.documents WHERE id = %s OR source = %s",
                     (doc_id, source))
        conn.execute("INSERT INTO rag_complex.documents VALUES (%s, %s, %s, %s)",
                     (doc_id, source, title, pages))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO rag_complex.chunks VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)",
                [(doc_id, i, c.kind, c.text, c.heading_context, c.page_start, c.page_end, vec(v))
                 for i, (c, v) in enumerate(zip(chunks, vectors, strict=True))],
            )


def vector_search(conn: Any, query_vec: list[float], n: int) -> list[dict]:
    rows = conn.execute(
        """SELECT c.document_id, c.ord, d.source, c.text, c.heading_context,
                  c.page_start, c.page_end
           FROM (SELECT *, embedding <=> %s::vector AS dist FROM rag_complex.chunks
                 ORDER BY dist LIMIT %s) c
           JOIN rag_complex.documents d ON d.id = c.document_id
           ORDER BY c.dist""",
        (vec(query_vec), n),
    ).fetchall()
    cols = ("document_id", "ord", "source", "text", "heading_context", "page_start", "page_end")
    return [{"id": f"{r[0]}-{r[1]}", **dict(zip(cols, r, strict=True))} for r in rows]
