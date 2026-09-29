import json
from unittest.mock import MagicMock

import pytest

import index_advisor.cli as cli
from index_advisor.bench import Result
from index_advisor.stats import TableStats, TopQuery


def _env(monkeypatch, key="x"):
    monkeypatch.setenv("KISENON_PROJECT_ID", "p")
    monkeypatch.setenv("KISENON_URL", "postgresql://main")
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "connect", lambda url: MagicMock())


def test_parser_defaults():
    a = cli.build_parser().parse_args(["advise"])
    assert (a.match, a.top, a.max_candidates, a.keep) == ("%", 5, 5, False)
    assert cli.build_parser().parse_args(["workload"]).rounds == 50


def test_check_exits_2_when_extension_missing(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setattr(cli, "check_pgss", lambda conn: "pg_stat_statements is not installed …")
    with pytest.raises(SystemExit) as e:
        cli.main(["check"])
    assert e.value.code == 2
    assert "not installed" in capsys.readouterr().err


def test_check_ok(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setattr(cli, "check_pgss", lambda conn: None)
    monkeypatch.setattr(cli, "top_queries", lambda conn, match, limit: [TopQuery("1", "q", 3, 9.0, 3.0)])
    assert cli.main(["check"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["pg_stat_statements"] == "ok"


def test_advise_exits_2_before_forking_when_pgss_missing(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr(cli, "check_pgss", lambda conn: "missing")
    monkeypatch.setattr(cli, "benchmark", lambda *a, **k: pytest.fail("must not fork"))
    with pytest.raises(SystemExit) as e:
        cli.main(["advise"])
    assert e.value.code == 2


def test_advise_exits_2_when_no_statements(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setattr(cli, "check_pgss", lambda conn: None)
    monkeypatch.setattr(cli, "top_queries", lambda conn, match, limit: [])
    with pytest.raises(SystemExit) as e:
        cli.main(["advise"])
    assert e.value.code == 2
    assert "index-advisor workload" in capsys.readouterr().err


def test_advise_missing_key_exits_2(monkeypatch, capsys):
    _env(monkeypatch, key="")
    with pytest.raises(SystemExit) as e:
        cli.main(["advise"])
    assert e.value.code == 2
    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_advise_happy_path(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setattr(cli, "check_pgss", lambda conn: None)
    monkeypatch.setattr(cli, "top_queries",
                        lambda conn, match, limit: [TopQuery("7", "SELECT … $1", 50, 4200.0, 84.0)])
    monkeypatch.setattr(cli, "table_stats", lambda conn: {"orders": TableStats("orders", 1, 1)})
    monkeypatch.setattr(cli, "describe_schema", lambda conn, stats: "index_advisor.orders(id bigint)")
    monkeypatch.setattr(cli, "complete", lambda *a, **k: json.dumps({"candidates": [{
        "queryid": "7", "table": "index_advisor.orders",
        "index_sql": "CREATE INDEX ON index_advisor.orders (customer_id)",
        "sample_query": "SELECT 1 FROM index_advisor.orders WHERE customer_id = 1", "why": "w"}]}))
    seen = {}

    def fake_bench(p, project, name, keep, stats, calls):
        seen.update(name=name, calls=calls)
        return Result(p, name, 80.0, 0.5, 8192, True, calls, 3975.0, "note", None)
    monkeypatch.setattr(cli, "benchmark", fake_bench)
    assert cli.main(["advise"]) == 0
    assert seen["calls"] == 50 and seen["name"].startswith("index-advisor-")
    out = capsys.readouterr().out
    assert "CREATE INDEX CONCURRENTLY ON index_advisor.orders (customer_id);" in out
    assert json.loads(out.strip().splitlines()[-1])["recommendations"][0]["used"] is True


def test_workload_prints_count(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setattr(cli, "run_workload", lambda conn, rounds: rounds * 3)
    assert cli.main(["workload", "--rounds", "2"]) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == {"statements": 6}
