import json

import pytest

from seed_snapshots import cli, keon


@pytest.fixture
def fake(monkeypatch):
    log = []
    ids = {"main": "br_main", "fixture-small": "br_small"}
    counter = iter(range(100))
    monkeypatch.setenv("KISENON_PROJECT_ID", "proj_1")
    monkeypatch.setattr(keon, "branch_ids", lambda **kw: dict(ids))

    def create(**kw):
        b = keon.Branch(name=kw["name"], id=f"br_{next(counter)}")
        log.append(("create", kw["name"], kw["parent_id"], b.id))
        return b
    monkeypatch.setattr(keon, "create_branch", create)
    monkeypatch.setattr(keon, "get_branch_url", lambda **kw: "postgresql://u:p@h/db")
    monkeypatch.setattr(keon, "reset_branch", lambda **kw: log.append(("reset", kw["branch_id"])))
    monkeypatch.setattr(keon, "delete_branch",
                        lambda **kw: log.append(("delete", kw["branch_id"])))

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cli.psycopg, "connect", lambda url: Conn())
    monkeypatch.setattr(cli, "seed", lambda conn, fixture: log.append(("seed", fixture)))
    monkeypatch.setattr(cli, "count_orders", lambda url: 1000)
    return log


def last_json(out):
    return json.loads(out.strip().splitlines()[-1])


def test_build_skips_existing_and_builds_missing(fake, capsys):
    assert cli.main(["build"]) == 0
    record = last_json(capsys.readouterr().out)
    assert [b["fixture"] for b in record["built"]] == ["empty", "prodlike"]
    creates = [e for e in fake if e[0] == "create"]
    assert [c[1] for c in creates] == ["fixture-empty", "fixture-prodlike"]
    assert all(c[2] == "br_main" for c in creates)
    assert ("seed", "prodlike") in fake


def test_build_rebuild_deletes_first(fake):
    assert cli.main(["build", "--fixture", "small", "--rebuild"]) == 0
    assert fake[0] == ("delete", "br_small")
    assert fake[1][:3] == ("create", "fixture-small", "br_main")


def test_timing_measures_three_methods_and_cleans_up(fake, capsys):
    assert cli.main(["timing", "--fixture", "small", "--runs", "2"]) == 0
    record = last_json(capsys.readouterr().out)
    assert set(record["runs_ms"]) == {"reseed", "fork", "reset"}
    assert all(len(v) == 2 for v in record["runs_ms"].values())
    created = {e[3] for e in fake if e[0] == "create"}
    deleted = {e[1] for e in fake if e[0] == "delete"}
    assert created == deleted
    assert [e for e in fake if e[0] == "reset"] == [("reset", "br_3")] * 2


def test_timing_cleans_up_on_failure(fake, monkeypatch):
    def boom(url):
        raise cli.psycopg.OperationalError("down")
    monkeypatch.setattr(cli, "count_orders", boom)
    assert cli.main(["timing", "--fixture", "small", "--runs", "1"]) == 1
    created = {e[3] for e in fake if e[0] == "create"}
    deleted = {e[1] for e in fake if e[0] == "delete"}
    assert created == deleted


def test_timing_without_fixture_branch_exits_2(fake):
    assert cli.main(["timing", "--fixture", "prodlike"]) == 2


def test_missing_project_exits_2(monkeypatch):
    monkeypatch.delenv("KISENON_PROJECT_ID", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    assert cli.main(["build"]) == 2
