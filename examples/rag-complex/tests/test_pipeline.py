import hashlib
import json
from types import SimpleNamespace

from rag_complex import pipeline
from rag_complex.embed import Embedder


def test_ingest_reads_mineru_layout_and_writes_both_stores(tmp_path, monkeypatch):
    (tmp_path / "pdfs").mkdir()
    (tmp_path / "pdfs" / "2204.00498.pdf").write_bytes(b"%PDF fake")
    auto = tmp_path / "parsed" / "2204.00498" / "auto"
    auto.mkdir(parents=True)
    (auto / "2204.00498_content_list.json").write_text(json.dumps([
        {"type": "text", "text": "Paper Title", "text_level": 1, "page_idx": 0},
        {"type": "text", "text": "Body.", "page_idx": 1},
    ]))
    (auto / "2204.00498_content_list_v2.json").write_text("[]")  # must be ignored

    calls = SimpleNamespace(schema=None, doc=None)
    def ensure_schema(conn, name, dim, chunker, *, reset):
        calls.schema = (name, dim, chunker, reset)

    monkeypatch.setattr(pipeline.store, "ensure_schema", ensure_schema)
    monkeypatch.setattr(pipeline.store, "replace_document",
                        lambda conn, *args: setattr(calls, "doc", args))

    class FakeMeili:
        def __init__(self):
            self.ops = []

        def delete_index(self, index):
            self.ops.append(("delete", index))

        def ensure_index(self, index):
            self.ops.append(("ensure", index))

        def replace_document(self, index, doc_id, docs):
            self.ops.append(("replace", index, doc_id, docs))

    meili = FakeMeili()
    emb = Embedder("fake", 2, 1000, lambda texts: [[1.0, 0.0]] * len(texts), lambda q: [1.0, 0.0])
    summary = pipeline.ingest(None, meili, "chunks_main", parsed_dir=tmp_path / "parsed",
                              pdf_dir=tmp_path / "pdfs", chunker="block", embedder=emb,
                              reset=True)

    doc_id = hashlib.sha256(b"%PDF fake").hexdigest()[:24]
    assert calls.schema == ("fake", 2, "block", True)
    assert calls.doc[:4] == (doc_id, "2204.00498", "Paper Title", 2)
    assert [op[0] for op in meili.ops] == ["delete", "ensure", "replace"]
    docs = meili.ops[2][3]
    assert docs[1] == {"id": f"{doc_id}-1", "document_id": doc_id, "ord": 1,
                       "source": "2204.00498", "text": "Body.", "heading_context": "Paper Title",
                       "page_start": 2, "page_end": 2}
    assert (summary["documents"], summary["chunks"]) == (1, 2)
