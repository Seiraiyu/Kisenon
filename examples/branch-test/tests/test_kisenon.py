import json
import subprocess

import pytest

from branch_test.kisenon import (
    Branch,
    KeonError,
    KeonNotFound,
    create_branch,
    delete_branch,
    get_branch_url,
)


def _fake_completed(
    stdout: str, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["keon"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_create_branch_returns_branch_with_name(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kw):
        calls.append(args)
        return _fake_completed(json.dumps({"name": "auto-name", "id": "br_42"}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    branch = create_branch(project="proj_1", name="auto-name", parent="main")
    assert branch.name == "auto-name"
    assert calls[0][:2] == ["keon", "branches"]
    assert "--project" in calls[0]
    assert "proj_1" in calls[0]
    assert "--name" in calls[0]
    assert "auto-name" in calls[0]
    assert "--parent" in calls[0]
    assert "main" in calls[0]


def test_get_branch_url_parses_url_field(monkeypatch):
    def fake_run(args, **kw):
        return _fake_completed(json.dumps({"url": "postgresql://x:y@h/main?sslmode=require"}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    url = get_branch_url(project="proj_1", branch="auto-name")
    assert url.startswith("postgresql://")


def test_get_branch_url_handles_alternate_key(monkeypatch):
    """Some `keon` versions may return `connection_string` instead of `url`."""
    def fake_run(args, **kw):
        return _fake_completed(json.dumps({"connection_string": "postgresql://abc"}))

    monkeypatch.setattr(subprocess, "run", fake_run)
    url = get_branch_url(project="proj_1", branch="x")
    assert url == "postgresql://abc"


def test_delete_branch_invokes_correct_subcommand(monkeypatch):
    captured: list[list[str]] = []

    def fake_run(args, **kw):
        captured.append(args)
        return _fake_completed("")

    monkeypatch.setattr(subprocess, "run", fake_run)
    delete_branch(project="proj_1", branch="auto-name")
    assert "delete" in captured[0]
    assert "auto-name" in captured[0]


def test_keon_not_found_raises_specific_error(monkeypatch):
    def fake_run(args, **kw):
        raise FileNotFoundError("keon")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(KeonNotFound):
        create_branch(project="proj_1", name="x", parent="main")


def test_keon_nonzero_exit_raises_keon_error(monkeypatch):
    def fake_run(args, **kw):
        return _fake_completed("", returncode=1, stderr="permission denied")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(KeonError, match="permission denied"):
        create_branch(project="proj_1", name="x", parent="main")


def test_branch_dataclass_has_created_in_ms_field():
    b = Branch(name="x", id="i", created_in_ms=123)
    assert b.created_in_ms == 123
