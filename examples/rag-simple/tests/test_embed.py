import pytest

from rag_simple.embed import get_embedder


def test_unknown_embedder_raises():
    with pytest.raises(ValueError, match="unknown embedder"):
        get_embedder("word2vec")
