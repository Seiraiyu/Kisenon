import json
from pathlib import Path

from rag_complex.chunker import CHUNKERS, MAX_CHARS, block_chunks, embed_text

ITEMS = json.loads((Path(__file__).parent / "fixtures" / "sample_content_list.json").read_text())


def test_block_drops_headers_footers_page_numbers_refs_and_empty_images():
    texts = [c.text for c in block_chunks(ITEMS)]
    assert "Preprint. Under review." not in texts
    assert "1" not in texts
    assert "Tiny Paper, 2026" not in texts
    assert not any("Someone. A paper." in t for t in texts)
    assert len(texts) == 9


def test_titles_are_own_chunks_and_set_heading_context():
    chunks = block_chunks(ITEMS)
    title = chunks[0]
    assert (title.kind, title.text, title.heading_context) == (
        "title", "A Tiny Paper About Tables", "A Tiny Paper About Tables")
    body = next(c for c in chunks if c.text == "Tables are useful.")
    assert body.heading_context == "A Tiny Paper About Tables > 1 Introduction"


def test_sibling_heading_replaces_and_child_heading_nests():
    chunks = block_chunks(ITEMS)
    table = next(c for c in chunks if c.kind == "table")
    assert table.heading_context == "A Tiny Paper About Tables > 2 Results"
    ablation = next(c for c in chunks if c.text.startswith("Removing"))
    assert ablation.heading_context == "A Tiny Paper About Tables > 2 Results > 2.1 Ablations"


def test_table_passthrough_keeps_html_caption_and_footnote():
    table = next(c for c in block_chunks(ITEMS) if c.kind == "table")
    assert table.text.splitlines()[0] == "Table 1: Accuracy by model."
    assert "<td>91.2</td>" in table.text
    assert table.text.endswith("Higher is better.")
    assert (table.page_start, table.page_end) == (2, 2)  # page_idx is 0-based


def test_oversized_text_is_split():
    items = [{"type": "text", "text": "x" * (MAX_CHARS * 2 + 5), "page_idx": 0}]
    assert [len(c.text) for c in block_chunks(items)] == [MAX_CHARS, MAX_CHARS, 5]


def test_heading_merge_groups_blocks_under_the_same_heading():
    chunks = CHUNKERS["heading-merge"](ITEMS)
    intro = next(c for c in chunks if c.text.startswith("1 Introduction"))
    assert intro.text == "1 Introduction\n\nTables are useful."
    results = next(c for c in chunks if c.text.startswith("2 Results"))
    assert "<table>" in results.text and "frac" in results.text
    assert (results.page_start, results.page_end) == (2, 2)


def test_fixed_merges_across_headings_up_to_limit():
    chunks = CHUNKERS["fixed"](ITEMS)
    assert len(chunks) == 1
    assert (chunks[0].page_start, chunks[0].page_end, chunks[0].kind) == (1, 3, "merged")


def test_embed_text_prefixes_heading_context():
    c = block_chunks(ITEMS)[1]
    assert embed_text(c) == "A Tiny Paper About Tables\n\nWe measure things and put them in tables."
