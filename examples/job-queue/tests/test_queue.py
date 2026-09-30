from unittest.mock import MagicMock

import pytest

from job_queue import queue


def test_backoff_doubles_and_caps():
    assert [queue.backoff_s(a) for a in (1, 2, 3, 10)] == [2, 4, 8, 60]


def test_next_state_retries_until_max_attempts():
    assert queue.next_state(1, 4) == ("queued", 2)
    assert queue.next_state(3, 4) == ("queued", 8)
    assert queue.next_state(4, 4) == ("failed", 0)


def _conn_with_claim(row):
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = row
    return conn


def test_run_one_empty_queue_returns_none():
    assert queue.run_one(_conn_with_claim(None), "w1", lambda p: None) is None


def test_run_one_success_marks_done():
    conn = _conn_with_claim((7, {"n": 1}, 0, 4))
    assert queue.run_one(conn, "w1", lambda p: None) == (7, "done")
    sql, params = conn.execute.call_args.args
    assert "status = 'done'" in sql and params == (1, "w1", 7)
    conn.transaction.assert_called_once()


def test_run_one_failure_schedules_retry_with_backoff():
    conn = _conn_with_claim((7, {}, 1, 4))

    def boom(p):
        raise RuntimeError("simulated failure")

    assert queue.run_one(conn, "w1", boom) == (7, "retry")
    params = conn.execute.call_args.args[1]
    assert params == ("queued", 2, 4, "simulated failure", "w1", 7)


def test_run_one_last_attempt_marks_failed():
    conn = _conn_with_claim((7, {}, 3, 4))

    def boom(p):
        raise RuntimeError("x")

    assert queue.run_one(conn, "w1", boom) == (7, "failed")
    assert conn.execute.call_args.args[1][0] == "failed"


def test_claim_sql_skips_locked_rows():
    assert "FOR UPDATE SKIP LOCKED" in queue.CLAIM_SQL


def test_enqueue_inserts_and_notifies_in_one_transaction():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    queue.enqueue(conn, [{"n": 1}, {"n": 2}])
    conn.transaction.assert_called_once()
    assert len(cur.executemany.call_args.args[1]) == 2
    assert conn.execute.call_args.args[0] == "NOTIFY job_queue"


@pytest.mark.parametrize("url,expected", [
    ("postgresql://u:p@ep-pooler.usc1.kisenon.com:5432/main", True),
    ("postgresql://u:p@ep.usc1.kisenon.com:5432/main", False),
])
def test_is_pooled(url, expected):
    assert queue.is_pooled(url) is expected
