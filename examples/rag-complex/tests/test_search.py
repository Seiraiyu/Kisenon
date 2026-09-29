from types import SimpleNamespace

import pytest

from rag_complex import search as search_mod
from rag_complex.search import rrf, search


def test_rrf_sums_reciprocal_ranks_with_k60():
    fused = rrf({"vector": ["a", "b"], "keyword": ["b", "c"]})
    assert [key for key, _, _ in fused] == ["b", "a", "c"]
    key, score, ranks = fused[0]
    assert score == pytest.approx(1 / 62 + 1 / 61)
    assert ranks == {"vector": 2, "keyword": 1}
    assert fused[1][2] == {"vector": 1}
    assert fused[2][2] == {"keyword": 2}


def _hit(i):
    return {"id": i, "text": f"text {i}", "source": "s", "page_start": 1, "page_end": 1}


@pytest.fixture
def fakes(monkeypatch):
    calls = {}

    def vector_search(conn, qvec, n):
        calls["vector_n"] = n
        return [_hit("a"), _hit("b")]

    monkeypatch.setattr(search_mod.store, "vector_search", vector_search)

    class FakeMeili:
        def search(self, index, q, limit):
            calls["keyword"] = (index, q, limit)
            return [_hit("b"), _hit("c")]

    embedder = SimpleNamespace(embed_query=lambda q: [0.1])
    return calls, FakeMeili(), embedder


def test_hybrid_fetches_2k_from_both_and_reports_contributions(fakes):
    calls, meili, emb = fakes
    hits = search("q", conn=None, meili=meili, index="chunks_main", embedder=emb, k=3)
    assert calls["vector_n"] == 6 and calls["keyword"] == ("chunks_main", "q", 6)
    assert [h["id"] for h in hits] == ["b", "a", "c"]
    assert hits[0]["contributions"] == {"vector": 2, "keyword": 1, "rerank": None}
    assert hits[1]["contributions"] == {"vector": 1, "keyword": None, "rerank": None}


def test_semantic_and_keyword_modes_use_one_list(fakes):
    _, meili, emb = fakes
    sem = search("q", conn=None, meili=meili, index="i", embedder=emb, mode="semantic")
    assert [h["id"] for h in sem] == ["a", "b"]
    kw = search("q", conn=None, meili=meili, index="i", embedder=emb, mode="keyword")
    assert [h["id"] for h in kw] == ["b", "c"]


def test_reranker_reorders_and_records_score(fakes):
    _, meili, emb = fakes

    def rerank(q, docs):
        return [(2, 0.9), (0, 0.5), (1, 0.1)]  # c, b, a

    hits = search("q", conn=None, meili=meili, index="i", embedder=emb, k=2, reranker=rerank)
    assert [h["id"] for h in hits] == ["c", "b"]
    assert hits[0]["contributions"] == {"vector": None, "keyword": 2, "rerank": 0.9}
