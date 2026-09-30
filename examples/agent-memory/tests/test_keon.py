import json
import subprocess

import pytest

from agent_memory.keon import KeonError, KeonNotFound, create_branch, delete_branch, get_branch_url


def _done(stdout: str, rc: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["keon"], returncode=rc, stdout=stdout, stderr=stderr)


def test_create_branch_waits_and_returns_id(monkeypatch):
    calls = []

    def fake(args, **kw):
        calls.append(args)
        return _done(json.dumps({"branch": {"id": "br_1", "name": "agent-memory-x"}}))

    monkeypatch.setattr(subprocess, "run", fake)
    assert create_branch(project="p", name="agent-memory-x") == "br_1"
    assert calls[0][:2] == ["keon", "branches"] and "--wait" in calls[0]
    assert calls[0][calls[0].index("--name") + 1] == "agent-memory-x"


def test_create_branch_without_id_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda a, **k: _done(json.dumps({"branch": {}})))
    with pytest.raises(KeonError, match="no branch id"):
        create_branch(project="p", name="x")


def test_get_branch_url(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda a, **k: _done(json.dumps({"connection_string": "postgresql://u:p@h/main"})),
    )
    assert get_branch_url(project="p", branch="x") == "postgresql://u:p@h/main"


def test_delete_branch_cascades(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda a, **k: calls.append(a) or _done(""))
    delete_branch(branch_id="br_1")
    assert calls[0] == ["keon", "branches", "delete", "--cascade", "br_1"]


def test_missing_binary(monkeypatch):
    def boom(a, **k):
        raise FileNotFoundError("keon")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(KeonNotFound):
        delete_branch(branch_id="x")


def test_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda a, **k: _done("", 1, "permission denied"))
    with pytest.raises(KeonError, match="permission denied"):
        delete_branch(branch_id="x")
