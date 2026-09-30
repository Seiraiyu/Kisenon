import pytest

from seed_snapshots import keon


@pytest.fixture
def calls(monkeypatch):
    log = []
    monkeypatch.setenv("KISENON_PROJECT_ID", "proj_1")
    monkeypatch.setattr(keon, "find_branch_id",
                        lambda **kw: log.append(("find", kw["name"])) or "fx_id")
    monkeypatch.setattr(keon, "create_branch",
                        lambda **kw: log.append(("create", kw["parent_id"]))
                        or keon.Branch(name=kw["name"], id="fork_id"))
    monkeypatch.setattr(keon, "get_branch_url", lambda **kw: "postgresql://u:p@h/db")
    monkeypatch.setattr(keon, "reset_branch", lambda **kw: log.append(("reset", kw["branch_id"])))
    monkeypatch.setattr(keon, "delete_branch",
                        lambda **kw: log.append(("delete", kw["branch_id"])))
    return log


TWO_TESTS = """
def test_a(kisenon_db):
    assert kisenon_db.startswith("postgresql://")

def test_b(kisenon_db):
    pass
"""


def test_forks_once_resets_after_each_test_then_deletes(pytester, calls):
    pytester.makepyfile(TWO_TESTS)
    result = pytester.runpytest_inprocess("--kisenon-fixture", "prodlike")
    result.assert_outcomes(passed=2)
    assert calls == [
        ("find", "fixture-prodlike"),
        ("create", "fx_id"),
        ("reset", "fork_id"),
        ("reset", "fork_id"),
        ("delete", "fork_id"),
    ]


def test_keep_skips_delete(pytester, calls):
    pytester.makepyfile(TWO_TESTS)
    pytester.runpytest_inprocess("--kisenon-keep").assert_outcomes(passed=2)
    assert ("delete", "fork_id") not in calls
    assert ("find", "fixture-small") in calls


def test_fork_deleted_when_a_test_fails(pytester, calls):
    pytester.makepyfile("def test_x(kisenon_db):\n    assert False\n")
    pytester.runpytest_inprocess().assert_outcomes(failed=1)
    assert calls[-1] == ("delete", "fork_id")


def test_missing_project_exits_2(pytester, calls, monkeypatch):
    monkeypatch.delenv("KISENON_PROJECT_ID")
    pytester.makepyfile(TWO_TESTS)
    assert pytester.runpytest_inprocess().ret == 2
    assert calls == []
