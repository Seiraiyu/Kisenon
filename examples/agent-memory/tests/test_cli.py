import json
from argparse import Namespace
from unittest.mock import MagicMock

import pytest

from agent_memory import cli


class FakeEmbedder:
    name = "fake"
    dim = 3

    def embed(self, texts, *, query=False):
        return [[0.0, 0.0, 1.0] for _ in texts]


@pytest.fixture
def env(monkeypatch):
    deleted: list[str] = []
    monkeypatch.setenv("DATABASE_URL", "postgresql://main")
    monkeypatch.setenv("KISENON_PROJECT_ID", "proj")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "get_embedder", lambda name: FakeEmbedder())
    monkeypatch.setattr(cli.signal, "signal", lambda *a: None)
    monkeypatch.setattr(cli.store, "connect", lambda url: MagicMock())
    monkeypatch.setattr(cli, "_prepare", lambda conn, embedder, reset: None)
    monkeypatch.setattr(cli.store, "fact_count", lambda conn: 3)
    monkeypatch.setattr(cli.keon, "create_branch", lambda project, name: "br_1")
    monkeypatch.setattr(cli.keon, "get_branch_url", lambda project, branch: "postgresql://fork")
    monkeypatch.setattr(cli.keon, "delete_branch", lambda branch_id: deleted.append(branch_id))
    return deleted


def test_what_if_deletes_fork_even_when_conversation_crashes(env, monkeypatch):
    def boom(*a):
        raise RuntimeError("llm down")

    monkeypatch.setattr(cli, "converse", boom)
    with pytest.raises(RuntimeError):
        cli.main(["say", "--what-if", "hi"])
    assert env == ["br_1"]


def test_what_if_keep_skips_delete(env, monkeypatch):
    monkeypatch.setattr(cli, "converse", lambda *a: [])
    assert cli.main(["say", "--what-if", "--keep", "hi"]) == 0
    assert env == []


def test_what_if_reports_main_unchanged(env, monkeypatch, capsys):
    monkeypatch.setattr(cli, "converse", lambda *a: [{"user": "hi"}])
    assert cli.main(["say", "--what-if", "hi"]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["what_if"]["deleted"] is True
    assert payload["what_if"]["main_facts_before"] == payload["what_if"]["main_facts_after"] == 3


def test_what_if_with_reset_is_rejected(env):
    with pytest.raises(SystemExit) as e:
        cli.main(["say", "--what-if", "--reset", "hi"])
    assert e.value.code == 2


def test_missing_database_url_exits_2(env, monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(SystemExit) as e:
        cli.main(["recall", "x"])
    assert e.value.code == 2


def test_converse_key_free_stores_message_verbatim(monkeypatch, capsys):
    monkeypatch.setattr(cli.store, "recall", lambda conn, vec: [])
    monkeypatch.setattr(cli.store, "recent_turns", lambda conn, session: [])
    monkeypatch.setattr(cli.store, "add_episode", lambda conn, s, r, c: 1)
    monkeypatch.setattr(cli.store, "upsert_fact", lambda conn, t, v, e: "added")
    args = Namespace(messages=["I like tea"], session="s", model="m")
    turns = cli.converse(MagicMock(), FakeEmbedder(), None, args)
    assert turns[0]["facts_added"] == ["I like tea"]
    assert "nothing yet" in turns[0]["assistant"]
    assert "Assistant: Recalled: nothing yet" in capsys.readouterr().out
