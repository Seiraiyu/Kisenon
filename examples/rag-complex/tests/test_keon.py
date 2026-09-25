import json
import subprocess

import pytest

from rag_complex.keon import KeonError, KeonNotFound, create_branch, delete_branch, get_branch_url


def _done(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(["keon"], returncode, stdout=stdout, stderr=stderr)


def test_create_branch_forks_main_and_waits(monkeypatch):
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return _done(json.dumps({"branch": {"id": "br_1", "name": "rag-exp-x"}}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert create_branch(project="p", name="rag-exp-x") == "br_1"
    assert calls[0] == ["keon", "branches", "create", "--project", "p", "--name", "rag-exp-x",
                        "--parent", "main", "--wait", "-o", "json"]


def test_create_branch_without_id_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda a, **k: _done(json.dumps({"branch": {}})))
    with pytest.raises(KeonError, match="no branch id"):
        create_branch(project="p", name="x")


def test_get_branch_url(monkeypatch):
    payload = json.dumps({"connection_string": "postgresql://u:p@h/main"})
    monkeypatch.setattr(subprocess, "run", lambda a, **k: _done(payload))
    assert get_branch_url(project="p", branch="x") == "postgresql://u:p@h/main"


def test_delete_branch_cascades(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda a, **k: calls.append(a) or _done())
    delete_branch(branch_id="br_1")
    assert calls == [["keon", "branches", "delete", "--cascade", "br_1"]]


def test_missing_binary_and_nonzero_exit(monkeypatch):
    def missing(a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(KeonNotFound):
        delete_branch(branch_id="x")
    monkeypatch.setattr(subprocess, "run", lambda a, **k: _done(returncode=1, stderr="denied"))
    with pytest.raises(KeonError, match="denied"):
        delete_branch(branch_id="x")
