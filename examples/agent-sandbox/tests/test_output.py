import base64
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from agent_sandbox.output import (
    _json_default,
    event,
    output_error,
    output_json,
    print_answer,
)


def test_output_json_writes_compact_to_stdout(capsys):
    output_json({"hello": "world"})
    out = capsys.readouterr()
    assert out.err == ""
    assert json.loads(out.out) == {"hello": "world"}


def test_print_answer_writes_human_line_to_stdout(capsys):
    print_answer("3,142 users would be removed.")
    out = capsys.readouterr()
    assert out.out.strip() == "Answer: 3,142 users would be removed."


def test_event_writes_bracketed_line_to_stderr(capsys):
    event("forking branch", duration_ms=547)
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.strip() == "[forking branch: 547ms]"


def test_event_with_no_fields_is_bare_label(capsys):
    event("agent done")
    out = capsys.readouterr()
    assert out.err.strip() == "[agent done]"


def test_event_multiple_fields_pipe_separated(capsys):
    event("run_sql", sql="SELECT 1", rows=1, duration_ms=8)
    out = capsys.readouterr()
    assert out.err.strip() == "[run_sql: SELECT 1 | rows=1 | duration_ms=8]"


def test_output_error_writes_json_to_stderr_and_exits(capsys, monkeypatch):
    monkeypatch.setattr(sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    try:
        output_error("boom", {"reason": "x"})
    except SystemExit as e:
        assert e.code == 1
    parsed = json.loads(capsys.readouterr().err)
    assert parsed == {"error": "boom", "reason": "x"}


def test_output_error_custom_exit_code(monkeypatch):
    monkeypatch.setattr(sys, "exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))
    try:
        output_error("nope", exit_code=2)
    except SystemExit as e:
        assert e.code == 2


def test_json_default_serializes_datetime_via_isoformat():
    dt = datetime(2026, 6, 16, 12, 34, 56, tzinfo=UTC)
    assert json.loads(json.dumps({"t": dt}, default=_json_default))["t"] == dt.isoformat()


def test_json_default_serializes_decimal_as_string():
    d = Decimal("3.14159")
    assert json.loads(json.dumps({"v": d}, default=_json_default))["v"] == "3.14159"


def test_json_default_serializes_uuid_as_string():
    u = UUID("12345678-1234-5678-1234-567812345678")
    assert json.loads(json.dumps({"id": u}, default=_json_default))["id"] == str(u)


def test_json_default_serializes_bytes_as_base64_dict():
    out = json.loads(json.dumps({"blob": b"hello"}, default=_json_default))
    assert out["blob"] == {"$bytes_b64": base64.b64encode(b"hello").decode()}
