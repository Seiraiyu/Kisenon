import json
import subprocess

import pytest

from kisenon_mcp.keon import KeonError, KeonNotFound, sandbox_create, sandbox_discard


def _done(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(["keon"], returncode, stdout=stdout, stderr=stderr)


def test_sandbox_create_sets_ttl_and_project(monkeypatch):
    calls = []
    payload = {"sandbox": {"id": "sb_1", "status": "active"},
               "sandbox_database_url": "postgresql://u:p@h/db"}

    def fake_run(args, **kw):
        calls.append(args)
        return _done(json.dumps(payload))

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert sandbox_create(project="proj", ttl_s=1800) == ("sb_1", "postgresql://u:p@h/db")
    assert calls[0] == ["keon", "sandbox", "create", "--budget-wall-seconds", "1800",
                        "--project", "proj", "-o", "json"]
    sandbox_create(project=None, ttl_s=60)
    assert "--project" not in calls[1]


def test_sandbox_create_without_url_raises(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda a, **k: _done(json.dumps({"sandbox": {"id": "sb_1"}})))
    with pytest.raises(KeonError, match="no id/url"):
        sandbox_create(project=None, ttl_s=60)


def test_nonzero_exit_and_missing_binary(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda a, **k: _done(returncode=1, stderr="forbidden"))
    with pytest.raises(KeonError, match="forbidden"):
        sandbox_discard("sb_1")

    def missing(a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(KeonNotFound):
        sandbox_discard("sb_1")
