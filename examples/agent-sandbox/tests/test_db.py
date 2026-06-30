from unittest.mock import MagicMock

import pytest

from agent_sandbox.db import (
    MultiStatementError,
    RunSqlResult,
    reject_multi_statement,
    run_sql,
)


def test_run_sql_result_dataclass_shape():
    r = RunSqlResult(
        sql="SELECT 1",
        rows_returned=1,
        rows_truncated=False,
        duration_ms=5,
        result_preview=[{"?column?": 1}],
        error=None,
    )
    assert r.rows_returned == 1
    assert r.error is None


def test_reject_multi_statement_accepts_single_statement():
    reject_multi_statement("SELECT 1")
    reject_multi_statement("UPDATE users SET name='x' WHERE id=1")
    reject_multi_statement("SELECT 1; ")
    reject_multi_statement("SELECT 1;\n")


def test_reject_multi_statement_rejects_two_statements():
    with pytest.raises(MultiStatementError):
        reject_multi_statement("SELECT 1; SELECT 2")


def test_reject_multi_statement_rejects_two_statements_no_space():
    with pytest.raises(MultiStatementError):
        reject_multi_statement("SELECT 1;SELECT 2")


def _mock_cursor(rows: list[tuple], description, rowcount: int):
    cur = MagicMock()
    cur.fetchall.return_value = rows
    cur.description = description
    cur.rowcount = rowcount
    return cur


def _mock_conn(cur):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn


def test_run_sql_captures_rows_and_rowcount():
    cur = _mock_cursor(
        rows=[(1, "alice"), (2, "bob")],
        description=[("id", None), ("name", None)],
        rowcount=2,
    )
    conn = _mock_conn(cur)
    result = run_sql(conn, "SELECT id, name FROM users", row_cap=10)
    assert result.rows_returned == 2
    assert result.rows_truncated is False
    assert result.result_preview == [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]
    assert result.duration_ms >= 0
    assert result.error is None
    cur.execute.assert_called_once_with("SELECT id, name FROM users")


def test_run_sql_rowcount_used_when_description_is_none():
    """psycopg returns description=None for non-SELECT statements (DELETE/UPDATE)."""
    cur = MagicMock()
    cur.description = None
    cur.rowcount = 3142
    conn = _mock_conn(cur)
    result = run_sql(
        conn,
        "DELETE FROM users WHERE last_login < NOW() - INTERVAL '2 years'",
        row_cap=10,
    )
    assert result.rows_returned == 3142
    assert result.result_preview == []
    assert result.rows_truncated is False
    assert result.error is None
    cur.fetchall.assert_not_called()


def test_run_sql_truncates_at_row_cap_and_flags():
    rows = [(i,) for i in range(50)]
    cur = _mock_cursor(rows=rows, description=[("i", None)], rowcount=50)
    conn = _mock_conn(cur)
    result = run_sql(conn, "SELECT i FROM generate_series(1, 50) i", row_cap=10)
    assert result.rows_returned == 50
    assert result.rows_truncated is True
    assert len(result.result_preview) == 10


def test_run_sql_captures_error_message_into_result():
    cur = MagicMock()
    cur.execute.side_effect = ValueError("syntax error at or near 'FROOM'")
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    result = run_sql(conn, "SELECT * FROOM users", row_cap=10)
    assert result.error is not None
    assert "syntax error" in result.error
    assert result.rows_returned == 0


def test_run_sql_multi_statement_raises_not_captured():
    """MultiStatementError is a caller bug, not a DB error."""
    conn = MagicMock()
    with pytest.raises(MultiStatementError):
        run_sql(conn, "SELECT 1; SELECT 2", row_cap=10)
