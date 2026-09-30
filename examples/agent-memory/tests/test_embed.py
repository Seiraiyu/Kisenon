from types import SimpleNamespace

import numpy as np
import pytest

from agent_memory.embed import EmbedderError, VoyageEmbedder, get_embedder


def test_voyage_requires_key(monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    with pytest.raises(EmbedderError, match="VOYAGE_API_KEY"):
        get_embedder("voyage")


def test_voyage_passes_input_type_and_returns_float32():
    calls = []

    class FakeClient:
        def embed(self, texts, model, input_type):
            calls.append((texts, model, input_type))
            return SimpleNamespace(embeddings=[[0.1] * 1024 for _ in texts])

    emb = object.__new__(VoyageEmbedder)
    emb._client = FakeClient()
    vecs = emb.embed(["q"], query=True)
    assert calls == [(["q"], "voyage-4-lite", "query")]
    assert vecs[0].dtype == np.float32 and vecs[0].shape == (1024,)
