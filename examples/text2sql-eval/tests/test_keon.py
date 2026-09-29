import json
import subprocess

import pytest

from text2sql_eval.keon import (
    Branch,
    KeonError,
    KeonNotFound,
    create_branch,
    delete_branch,
    find_branch_id,
    get_branch_url,
    list_branches,
)


def _completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["keon"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_list_branches_parses_branches_array(monkeypatch):
    def fake_run(args, **kw):
        return _completed(json.dumps({
            "branches": [
                {"id": "id_main", "name": "main"},
                {"id": "id_dev", "name": "dev"},
            ],
            "pagination": {},
        }))
    monkeypatch.setattr(subprocess, "run", fake_run)
    branches = list_branches(project="proj_1")
    assert [b.name for b in branches] == ["main", "dev"]
    assert branches[0].id == "id_main"


def test_find_branch_id_returns_match(monkeypatch):
    def fake_run(args, **kw):
        return _completed(json.dumps({"branches": [{"id": "id_main", "name": "main"}]}))
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert find_branch_id(project="proj_1", name="main") == "id_main"


def test_find_branch_id_raises_when_missing(monkeypatch):
    def fake_run(args, **kw):
        return _completed(json.dumps({"branches": []}))
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(KeonError, match="no branch named"):
        find_branch_id(project="proj_1", name="main")


def test_create_branch_returns_branch_with_id(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kw):
        calls.append(args)
        return _completed(json.dumps({
            "branch": {"name": "auto-name", "id": "br_42"},
            "operations": [],
        }))
    monkeypatch.setattr(subprocess, "run", fake_run)
    branch = create_branch(project="proj_1", name="auto-name", parent_id="parent_42")
    assert branch.name == "auto-name"
    assert branch.id == "br_42"
    assert "--project" in calls[0] and "proj_1" in calls[0]
    assert "--name" in calls[0] and "auto-name" in calls[0]
    assert "--parent-id" in calls[0] and "parent_42" in calls[0]


def test_get_branch_url_reads_connection_string(monkeypatch):
    def fake_run(args, **kw):
        return _completed(json.dumps({
            "connection_string": "postgresql://x:y@h/main?sslmode=require",
            "connection_uri": "postgresql://x:y@h/main?sslmode=require",
        }))
    monkeypatch.setattr(subprocess, "run", fake_run)
    url = get_branch_url(project="proj_1", branch="auto-name")
    assert url.startswith("postgresql://")


def test_get_branch_url_raises_when_field_missing(monkeypatch):
    def fake_run(args, **kw):
        return _completed(json.dumps({"foo": "bar"}))
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(KeonError, match="no connection_string"):
        get_branch_url(project="proj_1", branch="x")


def test_delete_branch_uses_cascade_positional(monkeypatch):
    captured: list[list[str]] = []

    def fake_run(args, **kw):
        captured.append(args)
        return _completed("")
    monkeypatch.setattr(subprocess, "run", fake_run)
    delete_branch(branch_id="br_42")
    assert captured[0] == ["keon", "branches", "delete", "--cascade", "br_42"]
    assert "--project" not in captured[0]


def test_keon_not_found_raises_specific_error(monkeypatch):
    def fake_run(args, **kw):
        raise FileNotFoundError("keon")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(KeonNotFound):
        list_branches(project="proj_1")


def test_keon_nonzero_exit_raises_keon_error(monkeypatch):
    def fake_run(args, **kw):
        return _completed("", returncode=1, stderr="permission denied")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(KeonError, match="permission denied"):
        list_branches(project="proj_1")


def test_branch_dataclass_carries_created_in_ms():
    b = Branch(name="x", id="i", created_in_ms=123)
    assert b.created_in_ms == 123


def test_create_branch_waits_for_ready(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kw):
        calls.append(args)
        return _completed(json.dumps({"branch": {"name": "n", "id": "b"}}))
    monkeypatch.setattr(subprocess, "run", fake_run)
    create_branch(project="p", name="n", parent_id="m")
    assert "--wait" in calls[0]


def test_reset_branch_calls_keon_reset(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kw):
        calls.append(args)
        return _completed("{}")
    monkeypatch.setattr(subprocess, "run", fake_run)
    from text2sql_eval.keon import reset_branch
    reset_branch(branch_id="br_9")
    assert calls[0] == ["keon", "branches", "reset", "br_9", "-o", "json"]


def _patch_fork(monkeypatch, deleted, delete_error=None):
    import text2sql_eval.keon as k
    monkeypatch.setattr(k, "find_branch_id", lambda project, name: "main_id")
    monkeypatch.setattr(
        k, "create_branch",
        lambda project, name, parent_id: Branch(name=name, id="br_1", created_in_ms=5),
    )
    monkeypatch.setattr(k, "get_branch_url", lambda project, branch: "postgresql://fork")

    def fake_delete(branch_id):
        if delete_error:
            raise delete_error
        deleted.append(branch_id)
    monkeypatch.setattr(k, "delete_branch", fake_delete)


def test_forked_yields_branch_and_url_then_deletes(monkeypatch):
    from text2sql_eval.keon import forked
    deleted: list[str] = []
    _patch_fork(monkeypatch, deleted)
    with forked(project="p", name="t-1") as (branch, url):
        assert branch.id == "br_1"
        assert url == "postgresql://fork"
    assert deleted == ["br_1"]


def test_forked_deletes_on_exception(monkeypatch):
    from text2sql_eval.keon import forked
    deleted: list[str] = []
    _patch_fork(monkeypatch, deleted)
    with pytest.raises(RuntimeError):
        with forked(project="p", name="t-1"):
            raise RuntimeError("boom")
    assert deleted == ["br_1"]


def test_forked_keep_skips_delete(monkeypatch):
    from text2sql_eval.keon import forked
    deleted: list[str] = []
    _patch_fork(monkeypatch, deleted)
    with forked(project="p", name="t-1", keep=True):
        pass
    assert deleted == []


def test_forked_cleanup_failure_prints_manual_command(monkeypatch, capsys):
    from text2sql_eval.keon import forked
    _patch_fork(monkeypatch, [], delete_error=KeonError("409"))
    with forked(project="p", name="t-1"):
        pass
    assert "keon branches delete --cascade br_1" in capsys.readouterr().err
