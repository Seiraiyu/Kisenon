"""Postgres storage in schema `agent_memory`: episodes (raw turns) + facts (embedded, deduped)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from pgvector.psycopg import register_vector

DEDUPE_SIMILARITY = 0.9  # cosine similarity at/above which a new fact merges into an existing one
HALF_LIFE_DAYS = 30.0  # recency weight halves every 30 days since a fact was last seen
CANDIDATES = 50  # nearest facts (HNSW) fetched before recency re-ranking

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS agent_memory;
CREATE TABLE IF NOT EXISTS agent_memory.meta (key text PRIMARY KEY, value text NOT NULL);
CREATE TABLE IF NOT EXISTS agent_memory.episodes (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session    text NOT NULL,
  role       text NOT NULL CHECK (role IN ('user', 'assistant')),
  content    text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS agent_memory.facts (
  id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  content        text NOT NULL,
  embedding      vector({dim}) NOT NULL,
  source_episode bigint REFERENCES agent_memory.episodes(id) ON DELETE SET NULL,
  hits           int NOT NULL DEFAULT 1,
  created_at     timestamptz NOT NULL DEFAULT now(),
  last_seen      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS facts_embedding_hnsw
  ON agent_memory.facts USING hnsw (embedding vector_cosine_ops);
"""


class DimMismatch(RuntimeError):
    def __init__(self, stored: int, wanted: int) -> None:
        super().__init__(
            f"agent_memory holds {stored}-d embeddings but this embedder is {wanted}-d. "
            "Switch --embedder back, or re-run with --reset (drops stored memories)."
        )


@dataclass(slots=True)
class Fact:
    id: int
    content: str
    similarity: float
    recency: float
    score: float


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=True)


def ensure_schema(conn: Any, dim: int, *, reset: bool = False) -> None:
    if reset:
        conn.execute("DROP SCHEMA IF EXISTS agent_memory CASCADE")
    conn.execute(SCHEMA_SQL.format(dim=int(dim)))
    row = conn.execute("SELECT value FROM agent_memory.meta WHERE key = 'embedding_dim'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO agent_memory.meta (key, value) VALUES ('embedding_dim', %s)", (str(dim),)
        )
    elif int(row[0]) != dim:
        raise DimMismatch(int(row[0]), dim)
    register_vector(conn)


def add_episode(conn: Any, session: str, role: str, content: str) -> int:
    return conn.execute(
        "INSERT INTO agent_memory.episodes (session, role, content) VALUES (%s, %s, %s) "
        "RETURNING id",
        (session, role, content),
    ).fetchone()[0]


def recent_turns(conn: Any, session: str, limit: int = 10) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT role, content FROM (SELECT id, role, content FROM agent_memory.episodes "
        "WHERE session = %s ORDER BY id DESC LIMIT %s) t ORDER BY id",
        (session, limit),
    ).fetchall()
    turns = [(r[0], r[1]) for r in rows]
    while turns and turns[0][0] == "assistant":  # Messages API wants user first
        turns.pop(0)
    return turns


def upsert_fact(conn: Any, content: str, embedding: Any, episode_id: int) -> str:
    """Insert a fact, or bump the nearest existing one if it's a near-duplicate."""
    nearest = conn.execute(
        "SELECT id, 1 - (embedding <=> %s) FROM agent_memory.facts "
        "ORDER BY embedding <=> %s LIMIT 1",
        (embedding, embedding),
    ).fetchone()
    if nearest is not None and nearest[1] >= DEDUPE_SIMILARITY:
        conn.execute(
            "UPDATE agent_memory.facts SET hits = hits + 1, last_seen = now() WHERE id = %s",
            (nearest[0],),
        )
        return "merged"
    conn.execute(
        "INSERT INTO agent_memory.facts (content, embedding, source_episode) VALUES (%s, %s, %s)",
        (content, embedding, episode_id),
    )
    return "added"


def rank(rows: list[tuple], *, k: int, now: datetime) -> list[Fact]:
    """score = similarity x 0.5 ** (age_days / HALF_LIFE_DAYS)."""
    facts = []
    for fact_id, content, similarity, last_seen in rows:
        age_days = max((now - last_seen).total_seconds() / 86400, 0.0)
        recency = 0.5 ** (age_days / HALF_LIFE_DAYS)
        facts.append(
            Fact(fact_id, content, round(float(similarity), 4), round(recency, 4),
                 round(float(similarity) * recency, 4))
        )
    return sorted(facts, key=lambda f: f.score, reverse=True)[:k]


def recall(conn: Any, query_vec: Any, *, k: int = 5) -> list[Fact]:
    rows = conn.execute(
        "SELECT id, content, 1 - (embedding <=> %s), last_seen FROM agent_memory.facts "
        "ORDER BY embedding <=> %s LIMIT %s",
        (query_vec, query_vec, CANDIDATES),
    ).fetchall()
    return rank(rows, k=k, now=datetime.now(UTC))


def fact_count(conn: Any) -> int:
    return conn.execute("SELECT count(*) FROM agent_memory.facts").fetchone()[0]
