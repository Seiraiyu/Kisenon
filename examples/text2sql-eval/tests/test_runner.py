from unittest.mock import MagicMock

import psycopg
import pytest

import text2sql_eval.runner as runner
from text2sql_eval.cases import Case, Outcome
from text2sql_eval.runner import connect, execute, extract_sql, mutated, run_eval


def _conn_with(cur):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn


def test_extract_sql_from_fence_and_plain():
    assert extract_sql("Here:\n```sql\nSELECT 1;\n```") == "SELECT 1"
    assert extract_sql("SELECT 2;  ") == "SELECT 2"


def test_execute_select_and_write():
    cur = MagicMock(description=[("n",)], statusmessage="SELECT 1", rowcount=1)
    cur.fetchall.return_value = [(750,)]
    o = execute(_conn_with(cur), "SELECT count(*) FROM users")
    assert (o.rows, o.status, o.error) == ([(750,)], "SELECT 1", None)

    cur = MagicMock(description=None, statusmessage="DELETE 100", rowcount=100)
    o = execute(_conn_with(cur), "DELETE FROM users")
    assert (o.rows, o.rowcount) == (None, 100)
    cur.fetchall.assert_not_called()


def test_execute_captures_errors():
    cur = MagicMock()
    cur.execute.side_effect = psycopg.errors.UndefinedTable("relation nope does not exist")
    o = execute(_conn_with(cur), "SELECT * FROM nope")
    assert o.error.startswith("UndefinedTable")


@pytest.mark.parametrize("status, expect", [
    ("SELECT 3", False), ("EXPLAIN", False), ("SHOW", False),
    ("DELETE 100", True), ("UPDATE 5", True), ("CREATE TABLE", True), ("DROP INDEX", True),
])
def test_mutated(status, expect):
    o = Outcome(sql="", rows=None, rowcount=0, status=status, error=None, duration_ms=0)
    assert mutated(o) is expect


def test_mutated_false_on_error():
    o = Outcome(sql="", rows=None, rowcount=None, status="", error="x", duration_ms=0)
    assert mutated(o) is False


def test_connect_retries_then_sets_search_path(monkeypatch):
    attempts = []
    good = MagicMock()

    def fake_connect(url, autocommit):
        attempts.append(url)
        if len(attempts) < 3:
            raise psycopg.OperationalError("endpoint not found")
        return good
    monkeypatch.setattr(psycopg, "connect", fake_connect)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    assert connect("postgresql://f") is good
    assert len(attempts) == 3
    good.execute.assert_any_call("SET search_path TO text2sql_eval")


def test_run_eval_resets_only_after_writes(monkeypatch):
    cases = [
        Case(id="read", question="how many?", expected_rows=[[1]]),
        Case(id="write", question="delete some", expected_rowcount=2),
        Case(id="read2", question="how many now?", expected_rows=[[1]]),
    ]
    outcomes = {
        "SELECT 1": Outcome("SELECT 1", [(1,)], 1, "SELECT 1", None, 3),
        "DELETE FROM t": Outcome("DELETE FROM t", None, 2, "DELETE 2", None, 4),
    }
    monkeypatch.setattr(runner, "execute", lambda conn, sql: outcomes[sql])
    monkeypatch.setattr(runner, "describe_schema", lambda conn: "t(id integer)")
    answers = {"how many?": "SELECT 1", "delete some": "DELETE FROM t",
               "how many now?": "SELECT 1"}
    seen_schema = []

    def ask(question, schema):
        seen_schema.append(schema)
        return f"```sql\n{answers[question]}\n```"

    connections = []
    resets = []

    def fake_connect():
        connections.append(MagicMock())
        return connections[-1]

    results = run_eval(cases, ask=ask, connect=fake_connect, reset_fork=lambda: resets.append(1))
    assert [r.match for r in results] == ["exact", "rowcount", "exact"]
    assert [r.reset for r in results] == [False, True, False]
    assert len(resets) == 1
    assert len(connections) == 2  # reconnect after the reset
    assert seen_schema == ["t(id integer)"] * 3
    assert all(c.close.called for c in connections)
