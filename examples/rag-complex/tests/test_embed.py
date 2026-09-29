from rag_complex.embed import Embedder, embed_batched


def fake_embedder(calls, *, max_batch=None, bad="BAD", budget=1000):
    def embed(texts):
        calls.append(list(texts))
        if (max_batch and len(texts) > max_batch) or any(bad in t for t in texts):
            raise RuntimeError("413 request too large")
        return [[float(len(t)), 1.0] for t in texts]

    return Embedder("fake", 2, budget, embed, lambda q: [0.0, 1.0])


def test_packs_batches_under_token_budget():
    calls: list[list[str]] = []
    texts = ["x" * 400] * 5  # ~101 tokens each
    vecs = embed_batched(texts, fake_embedder(calls, budget=250))
    assert [len(c) for c in calls] == [2, 2, 1]
    assert vecs == [[400.0, 1.0]] * 5


def test_max_items_caps_batch_size():
    calls: list[list[str]] = []
    embed_batched(["a"] * 5, fake_embedder(calls), max_items=2)
    assert [len(c) for c in calls] == [2, 2, 1]


def test_error_halves_batch_recursively():
    calls: list[list[str]] = []
    vecs = embed_batched(["a"] * 8, fake_embedder(calls, max_batch=2))
    assert [len(c) for c in calls] == [8, 4, 2, 2, 4, 2, 2]
    assert len(vecs) == 8


def test_single_failing_chunk_gets_zero_vector_and_warning():
    calls: list[list[str]] = []
    warnings: list[str] = []
    vecs = embed_batched(["ok", "BAD", "fine"], fake_embedder(calls), warn=warnings.append)
    assert vecs == [[2.0, 1.0], [0.0, 0.0], [4.0, 1.0]]
    assert len(warnings) == 1 and "zero vector" in warnings[0]
