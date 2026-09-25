from types import SimpleNamespace

from rag_simple.answer import MODEL, answer, format_context, format_sources

HITS = [
    {"source": "corpus/a.md", "ord": 0, "text": "Alpha text.", "score": 0.9},
    {"source": "corpus/b.txt", "ord": 3, "text": "Beta text.", "score": 0.8},
]


def test_format_context_numbers_sources_from_one():
    expected = "[1] (corpus/a.md)\nAlpha text.\n\n[2] (corpus/b.txt)\nBeta text."
    assert format_context(HITS) == expected


def test_format_sources_lists_citation_keys():
    assert format_sources(HITS).splitlines() == [
        "[1] corpus/a.md (chunk 0, score 0.9)",
        "[2] corpus/b.txt (chunk 3, score 0.8)",
    ]


class FakeMessages:
    def __init__(self, stop_reason="end_turn"):
        self.kwargs = None
        self.stop_reason = stop_reason

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[
                SimpleNamespace(type="thinking"),
                SimpleNamespace(type="text", text=" A [1]. "),
            ],
        )


def _client(stop_reason="end_turn"):
    msgs = FakeMessages(stop_reason)
    return SimpleNamespace(messages=msgs), msgs


def test_answer_sends_numbered_context_and_returns_text():
    client, msgs = _client()
    assert answer("What is alpha?", HITS, client=client) == "A [1]."
    assert msgs.kwargs["model"] == MODEL
    content = msgs.kwargs["messages"][0]["content"]
    assert "[1] (corpus/a.md)" in content and content.endswith("Question: What is alpha?")


def test_answer_handles_refusal():
    client, _ = _client("refusal")
    assert "declined" in answer("q", HITS, client=client)
