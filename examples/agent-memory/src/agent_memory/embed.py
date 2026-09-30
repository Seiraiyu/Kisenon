"""Embedders: fastembed (default: local CPU, no key) or Voyage (VOYAGE_API_KEY)."""
from __future__ import annotations

import os

import numpy as np


class EmbedderError(RuntimeError):
    """Embedder can't be constructed (e.g. missing key)."""


class FastEmbedder:
    name = "fastembed"
    model = "BAAI/bge-small-en-v1.5"
    dim = 384

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(self.model)

    def embed(self, texts: list[str], *, query: bool = False) -> list[np.ndarray]:
        vecs = self._model.query_embed(texts) if query else self._model.embed(texts)
        return [np.asarray(v, dtype=np.float32) for v in vecs]


class VoyageEmbedder:
    name = "voyage"
    model = "voyage-4-lite"
    dim = 1024

    def __init__(self) -> None:
        import voyageai

        self._client = voyageai.Client()  # reads VOYAGE_API_KEY

    def embed(self, texts: list[str], *, query: bool = False) -> list[np.ndarray]:
        out = self._client.embed(
            texts, model=self.model, input_type="query" if query else "document"
        )
        return [np.asarray(v, dtype=np.float32) for v in out.embeddings]


def get_embedder(name: str) -> FastEmbedder | VoyageEmbedder:
    if name == "voyage":
        if not os.environ.get("VOYAGE_API_KEY"):
            raise EmbedderError("VOYAGE_API_KEY is not set (needed for --embedder voyage).")
        return VoyageEmbedder()
    return FastEmbedder()
