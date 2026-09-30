import json

import pytest

from job_queue import cli


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@ep.usc1.kisenon.com/main")


def test_parser_defaults():
    a = cli.build_parser().parse_args(["demo"])
    got = (a.jobs, a.workers, a.fail_rate, a.work_ms, a.idle_s, a.poll_s)
    assert got == (40, 4, 0.2, 200, 3.0, 1.0)


def test_ping_ok(monkeypatch, capsys):
    monkeypatch.setattr(cli.queue, "ping", lambda url: 12.5)
    assert cli.main(["ping"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0] == "NOTIFY delivered in 12.5 ms"
    assert json.loads(out[-1]) == {"notify_delivered": True, "latency_ms": 12.5}


def test_ping_failure_prints_fallback_and_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(cli.queue, "ping", lambda url: None)
    assert cli.main(["ping"]) == 2
    err = capsys.readouterr().err
    assert "--poll-s" in err and "pooled" in err


def test_missing_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(SystemExit) as e:
        cli.main(["ping"])
    assert e.value.code == 2
