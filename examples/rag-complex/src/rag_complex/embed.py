"""Embedders plus a token-budget batcher that never fails the whole job."""
from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass

EMBEDDERS = ("fastembed", "voyage", "openai")
KEY_FOR = {"voyage": "VOYAGE_API_KEY", "openai": "OPENAI_API_KEY"}


@dataclass(slots=True)
class Embedder:
    name: str
    dim: int
    budget_tokens: int  # per request
    embed_documents: Callable[[list[str]], list[list[float]]]  # one request, no batching
    embed_query: Callable[[str], list[float]]


def get_embedder(name: str) -> Embedder:
    if name == "fastembed":
        from fastembed import TextEmbedding

        model = TextEmbedding("BAAI/bge-small-en-v1.5")
        return Embedder(
            name, 384, 8_000,
            lambda texts: [v.tolist() for v in model.embed(texts)],
            lambda q: next(iter(model.query_embed(q))).tolist(),
        )
    if name == "voyage":
        import voyageai

        vo = voyageai.Client()
        return Embedder(
            name, 1024, 100_000,
            lambda texts: vo.embed(texts, model="voyage-4", input_type="document").embeddings,
            lambda q: vo.embed([q], model="voyage-4", input_type="query").embeddings[0],
        )
    if name == "openai":
        from openai import OpenAI

        client = OpenAI()

        def openai_embed(texts: list[str]) -> list[list[float]]:
            resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
            return [d.embedding for d in resp.data]

        return Embedder(name, 1536, 100_000, openai_embed, lambda q: openai_embed([q])[0])
    raise ValueError(f"unknown embedder {name!r}; choose from {EMBEDDERS}")


def est_tokens(text: str) -> int:
    return len(text) // 4 + 1  # ponytail: chars/4 estimate; the halving below absorbs misses


def _warn(msg: str) -> None:
    sys.stderr.write(f"[warning: {msg}]\n")


def embed_batched(
    texts: list[str], embedder: Embedder, *, max_items: int = 128,
    warn: Callable[[str], None] = _warn,
) -> list[list[float]]:
    """Pack texts into batches under the token budget; on error halve the batch
    recursively; a single chunk that still fails gets a zero vector + warning."""
    batches: list[list[str]] = []
    cur: list[str] = []
    used = 0
    for t in texts:
        n = est_tokens(t)
        if cur and (used + n > embedder.budget_tokens or len(cur) >= max_items):
            batches.append(cur)
            cur, used = [], 0
        cur.append(t)
        used += n
    if cur:
        batches.append(cur)
    out: list[list[float]] = []
    for b in batches:
        out += _embed_or_halve(b, embedder, warn)
    return out


def _embed_or_halve(batch: list[str], embedder: Embedder, warn) -> list[list[float]]:
    try:
        vecs = embedder.embed_documents(batch)
        if len(vecs) != len(batch):
            raise ValueError(f"got {len(vecs)} vectors for {len(batch)} texts")
        return vecs
    except Exception as e:  # noqa: BLE001 — any failure: split and retry
        if len(batch) == 1:
            warn(f"embedding failed for one chunk ({type(e).__name__}: {e}); using a zero vector")
            return [[0.0] * embedder.dim]
        mid = len(batch) // 2
        return (_embed_or_halve(batch[:mid], embedder, warn)
                + _embed_or_halve(batch[mid:], embedder, warn))
