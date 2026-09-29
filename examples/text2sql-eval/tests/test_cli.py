import json
from contextlib import contextmanager

import pytest

import text2sql_eval.cli as cli
from text2sql_eval.keon import Branch
from text2sql_eval.runner import CaseResult


def test_parser_defaults():
    a = cli.build_parser().parse_args([])
    assert (a.cases, a.provider, a.model, a.keep, a.pretty) == (
        "cases.yaml", "anthropic", None, False, False,
    )


def test_missing_project_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("KISENON_PROJECT_ID", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert e.value.code == 2
    assert "KISENON_PROJECT_ID" in capsys.readouterr().err


def test_missing_key_exits_2_before_forking(monkeypatch, capsys):
    monkeypatch.setenv("KISENON_PROJECT_ID", "p")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "forked", lambda **kw: pytest.fail("must not fork"))
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert e.value.code == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def _fake_forked(**kw):
    @contextmanager
    def cm():
        yield Branch(name=kw["name"], id="br_1", created_in_ms=400), "postgresql://fork"
    return cm()


def _result(id_, match):
    return CaseResult(id=id_, question="q", sql="SELECT 1", executed=True, match=match,
                      reason="r", reset=False, duration_ms=2)


@pytest.mark.parametrize("matches, code", [(["exact", "set"], 0), (["exact", None], 1)])
def test_main_prints_table_and_json(monkeypatch, capsys, matches, code):
    monkeypatch.setenv("KISENON_PROJECT_ID", "p")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "forked", _fake_forked)
    monkeypatch.setattr(
        cli, "run_eval",
        lambda cases, ask, connect, reset_fork: [
            _result(f"c{i}", m) for i, m in enumerate(matches)
        ],
    )
    assert cli.main([]) == code
    out = capsys.readouterr().out.strip().splitlines()
    payload = json.loads(out[-1])
    assert payload["passed"] == matches.count("exact") + matches.count("set")
    assert payload["total"] == 2
    assert payload["branch"]["id"] == "br_1"
    assert out[0].startswith("case")
