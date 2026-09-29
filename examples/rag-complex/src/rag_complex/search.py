"""Hybrid search: pgvector + Meilisearch, fused with RRF, optionally reranked."""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from rag_complex import store

Reranker = Callable[[str, list[str]], list[tuple[int, float]]]  # -> (index, score)


def rrf(lists: dict[str, list[str]], k: int = 60) -> list[tuple[str, float, dict[str, int]]]:
    """Reciprocal rank fusion. Returns (key, score, {list_name: 1-based rank})."""
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for name, keys in lists.items():
        for rank, key in enumerate(keys, 1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            ranks.setdefault(key, {})[name] = rank
    return [(key, scores[key], ranks[key]) for key in sorted(scores, key=lambda x: -scores[x])]


def voyage_reranker() -> Reranker:
    import voyageai

    vo = voyageai.Client()

    def rerank(query: str, docs: list[str]) -> list[tuple[int, float]]:
        return [(r.index, r.relevance_score)
                for r in vo.rerank(query, docs, model="rerank-2").results]

    return rerank


def search(
    q: str, *, conn: Any, meili: Any, index: str, embedder: Any,
    mode: str = "hybrid", k: int = 10, reranker: Reranker | None = None,
) -> list[dict]:
    n = 2 * k

    def vector() -> list[dict]:
        return store.vector_search(conn, embedder.embed_query(q), n) if mode != "keyword" else []

    def keyword() -> list[dict]:
        return meili.search(index, q, n) if mode != "semantic" else []

    with ThreadPoolExecutor(2) as pool:
        fv, fk = pool.submit(vector), pool.submit(keyword)
        vhits, khits = fv.result(), fk.result()

    by_id: dict[str, dict] = {}
    for h in vhits + khits:
        by_id.setdefault(h["id"], h)
    fused = rrf({"vector": [h["id"] for h in vhits], "keyword": [h["id"] for h in khits]})[:n]
    hits = [
        {**by_id[key], "score": round(score, 5),
         "contributions": {"vector": r.get("vector"), "keyword": r.get("keyword"), "rerank": None}}
        for key, score, r in fused
    ]
    if reranker and hits:
        for i, s in reranker(q, [h["text"] for h in hits]):
            hits[i]["contributions"]["rerank"] = round(s, 4)
        hits.sort(key=lambda h: -(h["contributions"]["rerank"] or 0.0))
    return hits[:k]
