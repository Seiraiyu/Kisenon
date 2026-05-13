import subprocess

import pytest

from branch_test.schema_diff import (
    PgDumpNotFound,
    capture_schema,
    compute_diff,
    strip_noise,
)


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["pg_dump"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_strip_noise_removes_timestamp_comments():
    raw = (
        "-- Dumped from database version 17.0\n"
        "-- Dumped by pg_dump version 17.0\n"
        "-- Started on 2026-05-13 12:34:56\n"
        "-- Completed on 2026-05-13 12:34:57\n"
        "\n"
        "CREATE TABLE users (id INT);\n"
    )
    cleaned = strip_noise(raw)
    assert "Dumped from database" not in cleaned
    assert "CREATE TABLE users" in cleaned


def test_strip_noise_drops_trailing_blanks():
    raw = "CREATE TABLE x ();\n\n\n\n"
    cleaned = strip_noise(raw)
    # Trailing blank lines are removed; a single terminal newline remains.
    assert cleaned == "CREATE TABLE x ();\n"


def test_capture_schema_invokes_pg_dump(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kw):
        calls.append(args)
        return _completed("CREATE TABLE x ();\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    text = capture_schema("postgresql://x")
    assert "CREATE TABLE x ()" in text
    assert calls[0][0] == "pg_dump"
    assert "--schema-only" in calls[0]
    assert "--no-owner" in calls[0]
    assert "--no-acl" in calls[0]
    assert "postgresql://x" in calls[0]


def test_capture_schema_raises_when_pg_dump_missing(monkeypatch):
    def fake_run(args, **kw):
        raise FileNotFoundError("pg_dump")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(PgDumpNotFound):
        capture_schema("postgresql://x")


def test_capture_schema_raises_on_pg_dump_error(monkeypatch):
    def fake_run(args, **kw):
        return _completed("", returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="pg_dump failed"):
        capture_schema("postgresql://x")


def test_compute_diff_returns_empty_for_equal_schemas():
    a = "CREATE TABLE x ();\n"
    diff = compute_diff(a, a)
    assert diff == ""


def test_compute_diff_returns_unified_diff_when_different():
    before = "CREATE TABLE x (id INT);\n"
    after = "CREATE TABLE x (id INT, name TEXT);\n"
    diff = compute_diff(before, after)
    assert "+CREATE TABLE x (id INT, name TEXT)" in diff
    assert "-CREATE TABLE x (id INT)" in diff
