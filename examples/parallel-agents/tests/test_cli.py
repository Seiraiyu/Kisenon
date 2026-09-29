import json

import pytest

import parallel_agents.cli as cli
from parallel_agents.keon import Branch
from parallel_agents.race import Candidate


def _env(monkeypatch):
    monkeypatch.setenv("KISENON_PROJECT_ID", "p")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)


def test_parser_defaults():
    a = cli.build_parser().parse_args([])
    assert (a.query_file, a.goal_ms, a.strategies, a.keep) == (
        "dashboard.sql", 5.0, "index,rewrite,matview", False)


def test_unknown_strategy_exits_2(monkeypatch, capsys):
    _env(monkeypatch)
    with pytest.raises(SystemExit) as e:
        cli.main(["--strategies", "index,magic"])
    assert e.value.code == 2
    assert "magic" in capsys.readouterr().err


def test_missing_key_exits_2(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert e.value.code == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def _fake_race(candidates):
    async def fake(strategies, **kw):
        for c in candidates:
            if c.branch:
                kw["created"].append(c.branch)
        return candidates
    return fake


@pytest.mark.parametrize("keep", [False, True])
def test_main_deletes_losers_and_keeps_winner_only_with_keep(monkeypatch, capsys, keep):
    _env(monkeypatch)
    win = Candidate("index", Branch("a", "id-a"), ["CREATE INDEX x"], "q", "r", 80.0, 0.4, True)
    lose = Candidate("rewrite", Branch("b", "id-b"), [], "q2", "r", 80.0, 70.0, True)
    monkeypatch.setattr(cli, "race", _fake_race([win, lose]))
    deleted = []
    monkeypatch.setattr(cli, "delete_branch", lambda branch_id: deleted.append(branch_id))
    code = cli.main(["--keep"] if keep else [])
    assert code == 0
    assert deleted == (["id-b"] if keep else ["id-a", "id-b"])
    out = capsys.readouterr().out.strip().splitlines()
    payload = json.loads(out[-1])
    assert payload["winner"] == "index" and payload["met_goal"] is True
    assert any("Winner: index" in line for line in out)


def test_main_exit_1_when_goal_missed(monkeypatch):
    _env(monkeypatch)
    slow = Candidate("rewrite", Branch("b", "id-b"), [], "q", "", 80.0, 60.0, True)
    monkeypatch.setattr(cli, "race", _fake_race([slow]))
    monkeypatch.setattr(cli, "delete_branch", lambda branch_id: None)
    assert cli.main(["--strategies", "rewrite"]) == 1


def test_main_exit_2_when_no_fork_could_be_created(monkeypatch, capsys):
    _env(monkeypatch)
    failed = Candidate("index", error="KeonNotFound: `keon` is not on PATH")
    monkeypatch.setattr(cli, "race", _fake_race([failed]))
    with pytest.raises(SystemExit) as e:
        cli.main(["--strategies", "index"])
    assert e.value.code == 2
    assert "not on PATH" in capsys.readouterr().err
