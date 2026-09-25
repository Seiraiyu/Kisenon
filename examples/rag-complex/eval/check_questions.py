"""Validate eval/questions.jsonl against corpus/parsed.

Run from the example dir: uv run python eval/check_questions.py
"""
import collections
import json
import pathlib

from rag_complex.chunker import block_text

parsed = {f.parent.parent.name: json.loads(f.read_text())
          for f in pathlib.Path("corpus/parsed").glob("*/auto/*_content_list.json")}
rows = [json.loads(line) for line in pathlib.Path("eval/questions.jsonl").read_text().splitlines()
        if line.strip()]
assert len(rows) == 30, f"expected 30 questions, got {len(rows)}"
assert [r["id"] for r in rows] == [f"q{i:02d}" for i in range(1, 31)], "ids must be q01..q30"
for r in rows:
    assert set(r) == {"id", "question", "source", "page"}, r
    assert r["source"] in parsed, f"{r['id']}: unknown source {r['source']}"
    pages = {it.get("page_idx", 0) + 1 for it in parsed[r["source"]] if block_text(it)}
    assert r["page"] in pages, f"{r['id']}: page {r['page']} has no indexable block"
    assert len(r["question"]) >= 25, f"{r['id']}: question too short"
counts = collections.Counter(r["source"] for r in rows)
assert set(counts.values()) == {3} and len(counts) == 10, counts
print("ok: 30 questions, 3 per paper, all pages indexable")
