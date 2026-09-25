"""Embedders: fastembed (default, local, no key), voyage, openai."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

EMBEDDERS = ("fastembed", "voyage", "openai")
KEY_FOR = {"voyage": "VOYAGE_API_KEY", "openai": "OPENAI_API_KEY"}


@dataclass(slots=True)
class Embedder:
    name: str
    dim: int
    embed_documents: Callable[[list[str]], list[list[float]]]
    embed_query: Callable[[str], list[float]]


def get_embedder(name: str) -> Embedder:
    if name == "fastembed":
        from fastembed import TextEmbedding

        model = TextEmbedding("BAAI/bge-small-en-v1.5")
        return Embedder(
            name, 384,
            lambda texts: [v.tolist() for v in model.embed(texts)],
            lambda q: next(iter(model.query_embed(q))).tolist(),
        )
    if name == "voyage":
        import voyageai

        vo = voyageai.Client()

        def voyage_docs(texts: list[str]) -> list[list[float]]:
            out: list[list[float]] = []
            for i in range(0, len(texts), 128):
                batch = texts[i : i + 128]
                out += vo.embed(batch, model="voyage-4", input_type="document").embeddings
            return out

        return Embedder(
            name, 1024, voyage_docs,
            lambda q: vo.embed([q], model="voyage-4", input_type="query").embeddings[0],
        )
    if name == "openai":
        from openai import OpenAI

        client = OpenAI()

        def openai_embed(texts: list[str]) -> list[list[float]]:
            out: list[list[float]] = []
            for i in range(0, len(texts), 256):
                resp = client.embeddings.create(
                    model="text-embedding-3-small", input=texts[i : i + 256]
                )
                out += [d.embedding for d in resp.data]
            return out

        return Embedder(name, 1536, openai_embed, lambda q: openai_embed([q])[0])
    raise ValueError(f"unknown embedder {name!r}; choose from {EMBEDDERS}")
