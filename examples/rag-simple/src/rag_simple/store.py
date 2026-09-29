"""pgvector storage in the `rag_simple` schema."""
from __future__ import annotations

from typing import Any


class DimensionMismatch(RuntimeError):
    """The table was built with a different embedding dimension."""


def vec(v: list[float]) -> str:
    """pgvector text literal, passed as `%s::vector` (no numpy/pgvector adapter needed)."""
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def ensure_schema(conn: Any, dim: int, *, reset: bool = False) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute("CREATE SCHEMA IF NOT EXISTS rag_simple")
    if reset:
        conn.execute("DROP TABLE IF EXISTS rag_simple.chunks, rag_simple.meta")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rag_simple.meta (key text PRIMARY KEY, value text NOT NULL)"
    )
    conn.execute(
        "INSERT INTO rag_simple.meta (key, value) VALUES ('dim', %s) ON CONFLICT DO NOTHING",
        (str(dim),),
    )
    stored = int(conn.execute("SELECT value FROM rag_simple.meta WHERE key = 'dim'").fetchone()[0])
    if stored != dim:
        raise DimensionMismatch(
            f"chunks were embedded with dim={stored}, this embedder is dim={dim}. "
            "Re-ingest with --reset (or use the embedder you ingested with)."
        )
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS rag_simple.chunks (
              id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
              source    text NOT NULL,
              ord       int  NOT NULL,
              text      text NOT NULL,
              embedding vector({int(dim)}) NOT NULL,
              UNIQUE (source, ord))"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw "
        "ON rag_simple.chunks USING hnsw (embedding vector_cosine_ops)"
    )


def replace_source(conn: Any, source: str, chunks: list[str], vectors: list[list[float]]) -> None:
    """Idempotent re-ingest of one file: delete its old chunks, insert the new ones."""
    conn.execute("DELETE FROM rag_simple.chunks WHERE source = %s", (source,))
    for ord_, (text, v) in enumerate(zip(chunks, vectors, strict=True)):
        conn.execute(
            "INSERT INTO rag_simple.chunks (source, ord, text, embedding) "
            "VALUES (%s, %s, %s, %s::vector)",
            (source, ord_, text, vec(v)),
        )


def search(conn: Any, query_vec: list[float], k: int = 5) -> list[dict]:
    rows = conn.execute(
        "SELECT source, ord, text, 1 - (embedding <=> %s::vector) AS score "
        "FROM rag_simple.chunks ORDER BY embedding <=> %s::vector LIMIT %s",
        (vec(query_vec), vec(query_vec), k),
    ).fetchall()
    return [
        {"source": s, "ord": o, "text": t, "score": round(float(sc), 4)} for s, o, t, sc in rows
    ]
