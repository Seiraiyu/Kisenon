import json
import sys

from branch_test.output import (
    output_error,
    output_json,
    output_pretty,
    tail_truncate,
)


def test_output_json_writes_compact_to_stdout(capsys):
    output_json({"hello": "world"})
    out = capsys.readouterr()
    assert out.err == ""
    assert json.loads(out.out) == {"hello": "world"}


def test_output_pretty_calls_formatter(capsys):
    output_pretty({"x": 1}, lambda d: f"x={d['x']}")
    out = capsys.readouterr()
    assert out.out.strip() == "x=1"


def test_output_error_writes_json_to_stderr_and_exits(capsys, monkeypatch):
    monkeypatch.setattr(sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    try:
        output_error("boom", {"reason": "x"})
    except SystemExit as e:
        assert e.code == 1
    out = capsys.readouterr()
    parsed = json.loads(out.err)
    assert parsed["error"] == "boom"
    assert parsed["reason"] == "x"


def test_output_error_custom_exit_code(capsys, monkeypatch):
    monkeypatch.setattr(sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    try:
        output_error("nope", exit_code=2)
    except SystemExit as e:
        assert e.code == 2


def test_tail_truncate_returns_full_when_under_cap():
    body = "hello"
    text, truncated = tail_truncate(body, cap_bytes=100)
    assert text == "hello"
    assert truncated is False


def test_tail_truncate_keeps_last_n_bytes_when_over():
    body = "x" * 100 + "TAIL"
    text, truncated = tail_truncate(body, cap_bytes=4)
    assert text == "TAIL"
    assert truncated is True


def test_tail_truncate_handles_multibyte_safely():
    body = "ééé" * 50  # 6 bytes per char in utf-8 round-trip? actually 2 bytes each
    text, _ = tail_truncate(body, cap_bytes=10)
    # Decoded result must be a valid string (no broken surrogate halves).
    text.encode("utf-8")  # would raise if broken
