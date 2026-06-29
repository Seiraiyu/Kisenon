import json
import subprocess

import pytest

from agent_migrate.keon import (
    KeonError,
    KeonNotFound,
    SandboxRunResult,
    SandboxUnavailable,
    sandbox_discard,
    sandbox_log,
    sandbox_promote,
    sandbox_run,
)


def _completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess(args=["keon"], returncode=returncode,
                                       stdout=stdout, stderr=stderr)


def test_sandbox_run_parses_green(monkeypatch):
    payload = {
        "sandbox_id": "sb_1", "status": "green",
        "steps": [{"name": "migrate", "exit_code": 0}, {"name": "verify", "exit_code": 0}],
        "promote_preview": [{"seq": 1, "statement": "ALTER TABLE orders ADD COLUMN status text"}],
        "promote_hint": "keon sandbox promote sb_1",
    }
    captured = {}

    def fake_run(args, **kw):
        captured["args"] = args
        return _completed(json.dumps(payload), returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = sandbox_run(project="p", parent="main",
                    migrate_cmd="psql -f m.sql", verify_cmd="psql -f v.sql",
                    working_dir="/w", timeout_s=120)
    assert isinstance(r, SandboxRunResult)
    assert r.green is True and r.sandbox_id == "sb_1"
    assert r.promote_hint == "keon sandbox promote sb_1"
    a = captured["args"]
    assert a[:3] == ["keon", "sandbox", "run"]
    assert "--migrate" in a and "psql -f m.sql" in a
    assert "--verify" in a and "psql -f v.sql" in a
    assert "--parent" in a and "main" in a
    assert "--working-dir" in a and "/w" in a
    assert "--timeout-s" in a and "120" in a


def test_sandbox_run_red_is_not_fatal(monkeypatch):
    # `keon sandbox run` exits 1 on a red verdict but still prints valid JSON.
    payload = {"sandbox_id": "sb_2", "status": "red",
               "steps": [{"name": "verify", "exit_code": 1, "stderr_tail": "boom"}],
               "promote_preview": [], "promote_hint": "red — sandbox sb_2 preserved"}

    def fake_run(args, **kw):
        return _completed(json.dumps(payload), returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = sandbox_run(project="p", parent="main", migrate_cmd="psql -f m.sql")
    assert r.green is False and r.status == "red" and r.sandbox_id == "sb_2"


def test_sandbox_promote_returns_status(monkeypatch):
    def fake_run(args, **kw):
        return _completed(json.dumps({"sandbox": {"id": "sb_1", "status": "promoted"}}))
    monkeypatch.setattr(subprocess, "run", fake_run)
    sb = sandbox_promote(sandbox_id="sb_1")
    assert sb["status"] == "promoted"


def test_sandbox_promote_human_mode_parks(monkeypatch):
    def fake_run(args, **kw):
        return _completed(json.dumps({"sandbox": {"id": "sb_1", "status": "awaiting_approval"}}))
    monkeypatch.setattr(subprocess, "run", fake_run)
    sb = sandbox_promote(sandbox_id="sb_1")
    assert sb["status"] == "awaiting_approval"


def test_sandbox_discard(monkeypatch):
    captured = {}

    def fake_run(args, **kw):
        captured["args"] = args
        return _completed(json.dumps({"sandbox": {"id": "sb_1", "status": "discarded"}}))
    monkeypatch.setattr(subprocess, "run", fake_run)
    sb = sandbox_discard(sandbox_id="sb_1")
    assert sb["status"] == "discarded"
    assert captured["args"][:3] == ["keon", "sandbox", "discard"]


def test_sandbox_log_returns_actions(monkeypatch):
    def fake_run(args, **kw):
        return _completed(json.dumps({"actions": [{"seq": 1, "statement": "ALTER ..."}], "max_seq": 1}))
    monkeypatch.setattr(subprocess, "run", fake_run)
    actions = sandbox_log(sandbox_id="sb_1")
    assert actions[0]["seq"] == 1


def test_old_cli_without_sandbox_raises_unavailable(monkeypatch):
    def fake_run(args, **kw):
        return _completed("", returncode=1, stderr="error: unknown command 'sandbox'")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SandboxUnavailable, match="no `sandbox` command"):
        sandbox_run(project="p", parent="main", migrate_cmd="x")


def test_region_disabled_raises_unavailable(monkeypatch):
    def fake_run(args, **kw):
        return _completed(json.dumps({"code": "not_implemented",
                                      "message": "sandboxes are not yet available in this region"}),
                          returncode=1)
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SandboxUnavailable, match="not enabled"):
        sandbox_run(project="p", parent="main", migrate_cmd="x")


def test_keon_not_found(monkeypatch):
    def fake_run(args, **kw):
        raise FileNotFoundError("keon")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(KeonNotFound):
        sandbox_promote(sandbox_id="sb_1")


# KeonError is part of the public surface (base class for the others).
assert issubclass(KeonNotFound, KeonError)
assert issubclass(SandboxUnavailable, KeonError)
