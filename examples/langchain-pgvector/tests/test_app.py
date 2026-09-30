from langchain_core.documents import Document

import app


def test_load_docs_splits_md_and_tags_source(tmp_path):
    (tmp_path / "a.md").write_text("word " * 400)
    (tmp_path / "skip.txt").write_text("ignored")
    docs = app.load_docs(tmp_path)
    assert len(docs) > 1
    assert {d.metadata["source"] for d in docs} == {"a.md"}
    assert all(len(d.page_content) <= 800 for d in docs)


def test_format_docs_labels_each_chunk():
    out = app.format_docs([Document(page_content="x", metadata={"source": "a.md"})])
    assert out == "[a.md]\nx"


def test_missing_database_url_exits_2(monkeypatch):
    monkeypatch.setattr(app, "load_dotenv", lambda: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert app.main(["ask", "q"]) == 2


def test_bad_usage_exits_2(monkeypatch):
    monkeypatch.setattr(app, "load_dotenv", lambda: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert app.main(["nope"]) == 2
