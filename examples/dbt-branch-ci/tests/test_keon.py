import json
import subprocess

import pytest

from dbt_branch_ci import keon


def _done(stdout="", code=0, stderr=""):
    return subprocess.CompletedProcess(args=["keon"], returncode=code, stdout=stdout, stderr=stderr)


def test_find_branch_id(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda a, **kw: _done(json.dumps(
        {"branches": [{"id": "id_main", "name": "main"}]})))
    assert keon.find_branch_id(project="p", name="main") == "id_main"
    with pytest.raises(keon.KeonError, match="no branch named"):
        keon.find_branch_id(project="p", name="nope")


def test_create_branch_waits_and_uses_parent(monkeypatch):
    calls = []

    def fake(args, **kw):
        calls.append(args)
        return _done(json.dumps({"branch": {"id": "br_1", "name": "n"}}))
    monkeypatch.setattr(subprocess, "run", fake)
    assert keon.create_branch(project="p", name="n", parent_id="par").id == "br_1"
    assert "--wait" in calls[0] and calls[0][calls[0].index("--parent-id") + 1] == "par"


def test_get_branch_url_requires_field(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda a, **kw: _done("{}"))
    with pytest.raises(keon.KeonError, match="no connection_string"):
        keon.get_branch_url(project="p", branch="b")


def test_delete_uses_cascade(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda a, **kw: calls.append(a) or _done())
    keon.delete_branch(branch_id="br_1")
    assert calls[0] == ["keon", "branches", "delete", "--cascade", "br_1"]


def test_not_found_and_nonzero(monkeypatch):
    def missing(a, **kw):
        raise FileNotFoundError
    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(keon.KeonNotFound):
        keon.delete_branch(branch_id="x")
    monkeypatch.setattr(subprocess, "run", lambda a, **kw: _done(code=1, stderr="denied"))
    with pytest.raises(keon.KeonError, match="denied"):
        keon.delete_branch(branch_id="x")
