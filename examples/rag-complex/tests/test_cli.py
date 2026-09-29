import json
from types import SimpleNamespace

import pytest

from rag_complex import cli


def test_parser_defaults():
    a = cli.build_parser().parse_args(["experiment", "--chunker", "heading-merge",
                                       "--embedder", "voyage"])
    assert (a.chunker, a.embedder, a.keep, a.no_rerank) == ("heading-merge", "voyage", False, False)
    s = cli.build_parser().parse_args(["search", "q"])
    assert (s.mode, s.k) == ("hybrid", 10)


def test_missing_database_url_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert cli.main(["search", "q"]) == 2
    assert "DATABASE_URL" in json.loads(capsys.readouterr().err)["error"]


class FakeMeili:
    def __init__(self):
        self.deleted = []

    def delete_index(self, index):
        self.deleted.append(index)


@pytest.fixture
def exp(monkeypatch, tmp_path):
    qfile = tmp_path / "q.jsonl"
    qfile.write_text('{"id": "q1", "question": "q", "source": "s", "page": 1}\n')
    deleted = []
    monkeypatch.setenv("KISENON_PROJECT_ID", "proj")
    monkeypatch.setattr(cli, "embedder_for", lambda conn: SimpleNamespace(name="fastembed"))
    monkeypatch.setattr(cli, "read_meta", lambda conn: {"chunker": "block"})
    monkeypatch.setattr(cli.keon, "create_branch", lambda project, name: "br_1")
    monkeypatch.setattr(cli.keon, "delete_branch", lambda branch_id: deleted.append(branch_id))

    def boom(**kw):
        raise RuntimeError("fork url failed")

    monkeypatch.setattr(cli.keon, "get_branch_url", boom)
    args = cli.build_parser().parse_args(["experiment", "--questions", str(qfile)])
    return args, deleted


def test_experiment_deletes_fork_and_meili_index_on_failure(exp):
    args, deleted = exp
    meili = FakeMeili()
    with pytest.raises(RuntimeError, match="fork url failed"):
        cli.cmd_experiment(args, conn=None, meili=meili, reranker=None)
    assert deleted == ["br_1"]
    assert len(meili.deleted) == 1 and meili.deleted[0].startswith("chunks_rag-exp-")


def test_experiment_keep_skips_cleanup(exp):
    args, deleted = exp
    args.keep = True
    meili = FakeMeili()
    with pytest.raises(RuntimeError):
        cli.cmd_experiment(args, conn=None, meili=meili, reranker=None)
    assert deleted == [] and meili.deleted == []


def test_answer_cites_with_source_page_labels():
    captured = {}

    def create(**kw):
        captured.update(kw)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text="GPTQ [x p.2]")])

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    hits = [{"source": "x", "page_start": 2, "heading_context": "Results", "text": "t"}]
    assert cli.answer("q", hits, client=client) == "GPTQ [x p.2]"
    assert "[x p.2] (Results)\nt" in captured["messages"][0]["content"]
