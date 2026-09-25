from rag_simple.chunker import chunk_text


def test_short_text_is_one_chunk():
    assert chunk_text("hello\n\nworld") == ["hello\n\nworld"]


def test_empty_text_has_no_chunks():
    assert chunk_text("  \n\n  ") == []


def test_paragraphs_pack_up_to_size_and_carry_overlap():
    paras = [f"p{i:02d} " + "x" * 196 for i in range(10)]  # 10 x 200 chars
    chunks = chunk_text("\n\n".join(paras), size=800, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert nxt.startswith(prev[-100:])
    assert all(p in "".join(chunks) for p in paras)


def test_never_splits_inside_a_paragraph_that_fits():
    paras = ["a" * 500, "b" * 500]
    chunks = chunk_text("\n\n".join(paras), size=800, overlap=100)
    assert chunks[0] == "a" * 500
    assert "b" * 500 in chunks[1]


def test_long_paragraph_is_windowed_with_overlap():
    para = "".join(chr(ord("a") + i % 26) for i in range(2000))
    chunks = chunk_text(para, size=800, overlap=100)
    assert chunks[0] == para[:800]
    assert chunks[1].startswith(para[700:800])
    assert all(len(c) <= 800 for c in chunks)
    assert chunks[-1].endswith(para[-50:])
