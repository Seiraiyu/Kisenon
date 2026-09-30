import json

import pytest

from dbt_branch_ci import cli, compare, keon

URL = "postgresql://app:p%40ss@ep-1.kisenon.com:5432/main?sslmode=require"


def test_dbt_env_splits_url_and_unquotes_password():
    assert cli.dbt_env(URL) == {
        "DBT_HOST": "ep-1.kisenon.com",
        "DBT_PORT": "5432",
        "DBT_USER": "app",
        "DBT_ENV_SECRET_PASSWORD": "p@ss",
        "DBT_DBNAME": "main",
    }


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def fake(monkeypatch):
    calls = []
    monkeypatch.setenv("KISENON_PROJECT_ID", "proj_1")
    monkeypatch.setattr(keon, "find_branch_id", lambda **kw: "br_main")
    monkeypatch.setattr(keon, "create_branch",
                        lambda **kw: keon.Branch(name=kw["name"], id="br_fork"))
    monkeypatch.setattr(keon, "get_branch_url", lambda **kw: URL)
    monkeypatch.setattr(keon, "delete_branch", lambda **kw: calls.append(("delete", kw)))
    monkeypatch.setattr(cli, "run_dbt", lambda url: 0)
    monkeypatch.setattr(cli.psycopg2, "connect", lambda url: FakeConn())
    monkeypatch.setattr(compare, "relations_from_manifest", lambda path: [])
    snaps = iter([{"orders": (30, {"id": "integer"})}, {"orders": (29, {"id": "integer"})}])
    monkeypatch.setattr(compare, "snapshot", lambda conn, rels: next(snaps))
    return calls


def last_json(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


def test_check_passes_within_threshold_and_deletes_fork(fake, capsys):
    assert cli.main(["check"]) == 0
    record = last_json(capsys.readouterr().out)
    assert record["passed"] is True
    assert record["models"][0]["fork_rows"] == 29
    assert fake == [("delete", {"branch_id": "br_fork"})]


def test_check_fails_over_threshold(fake, capsys):
    assert cli.main(["check", "--max-row-delta-pct", "1"]) == 1
    out = capsys.readouterr().out
    assert "FAIL orders: row count 30 -> 29" in out
    assert last_json(out)["passed"] is False


def test_check_fails_when_dbt_build_fails_and_still_deletes(fake, monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_dbt", lambda url: 1)
    assert cli.main(["check"]) == 1
    assert last_json(capsys.readouterr().out)["failures"][0] == "dbt build failed (exit 1)"
    assert fake == [("delete", {"branch_id": "br_fork"})]


def test_check_keep_skips_delete(fake):
    assert cli.main(["check", "--keep"]) == 0
    assert fake == []


def test_fork_deleted_even_on_crash(fake, monkeypatch):
    def boom(url):
        raise RuntimeError("boom")
    monkeypatch.setattr(cli, "run_dbt", boom)
    with pytest.raises(RuntimeError):
        cli.main(["check"])
    assert fake == [("delete", {"branch_id": "br_fork"})]


def test_missing_project_exits_2(monkeypatch):
    monkeypatch.delenv("KISENON_PROJECT_ID", raising=False)
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    assert cli.main(["check"]) == 2


def test_keon_missing_exits_2(monkeypatch):
    monkeypatch.setenv("KISENON_PROJECT_ID", "proj_1")

    def missing(**kw):
        raise keon.KeonNotFound("`keon` is not on PATH")
    monkeypatch.setattr(keon, "find_branch_id", missing)
    assert cli.main(["check"]) == 2
