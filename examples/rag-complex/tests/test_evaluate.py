import pytest

from rag_complex.evaluate import first_relevant_rank, format_table, metrics, run_eval

Q = {"question": "q", "source": "2210.17323", "page": 5}


def h(source, start, end=None):
    return {"source": source, "page_start": start, "page_end": end or start}


def test_first_relevant_rank_matches_source_and_page_range():
    hits = [h("other", 5), h("2210.17323", 4), h("2210.17323", 4, 6)]
    assert first_relevant_rank(hits, Q) == 3
    assert first_relevant_rank([h("2210.17323", 6)], Q) is None


def test_metrics():
    m = metrics([1, 3, 7, None], [10, 20, 30, 40])
    assert m["recall@5"] == 0.5
    assert m["recall@10"] == 0.75
    assert m["mrr"] == pytest.approx(round((1 + 1 / 3 + 1 / 7) / 4, 3))
    assert m["p50_ms"] == 25.0


def test_run_eval_uses_search_fn_per_question():
    seen = []

    def search_fn(question):
        seen.append(question)
        return [h("2210.17323", 5)]

    m = run_eval([Q, Q], search_fn)
    assert seen == ["q", "q"]
    assert (m["recall@5"], m["mrr"]) == (1.0, 1.0)


def test_format_table_shows_deltas():
    a = {"recall@5": 0.5, "recall@10": 0.6, "mrr": 0.4, "p50_ms": 40.0}
    b = {"recall@5": 0.7, "recall@10": 0.6, "mrr": 0.45, "p50_ms": 38.5}
    table = format_table(a, b)
    assert "+0.200" in table and "-1.500" in table and "+0.000" in table
