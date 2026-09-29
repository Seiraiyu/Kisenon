import json

import pytest

from rag_simple.cli import build_parser, main


def test_parser_defaults():
    args = build_parser().parse_args(["ask", "what is kisenon?"])
    assert (args.question, args.k, args.embedder) == ("what is kisenon?", 5, "fastembed")
    args = build_parser().parse_args(["ingest", "corpus", "--reset", "--embedder", "voyage"])
    assert (str(args.dir), args.reset, args.embedder) == ("corpus", True, "voyage")


def test_parser_rejects_unknown_embedder():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["ask", "q", "--embedder", "nope"])


def test_missing_database_url_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("rag_simple.cli.load_dotenv", lambda: None)
    assert main(["ask", "q"]) == 2
    assert "DATABASE_URL" in json.loads(capsys.readouterr().err)["error"]


def test_missing_voyage_key_exits_2(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setattr("rag_simple.cli.load_dotenv", lambda: None)
    assert main(["ask", "q", "--embedder", "voyage"]) == 2
    assert "VOYAGE_API_KEY" in capsys.readouterr().err
