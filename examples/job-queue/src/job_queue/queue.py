"""Postgres job queue: SKIP LOCKED claims, retries with backoff, LISTEN/NOTIFY wakeups."""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

CHANNEL = "job_queue"
MAX_BACKOFF_S = 60

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS job_queue;
CREATE TABLE IF NOT EXISTS job_queue.jobs (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  payload      jsonb NOT NULL,
  status       text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'done', 'failed')),
  attempts     int NOT NULL DEFAULT 0,
  max_attempts int NOT NULL DEFAULT 4,
  run_at       timestamptz NOT NULL DEFAULT now(),
  last_error   text,
  last_worker  text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_ready ON job_queue.jobs (run_at, id) WHERE status = 'queued';
"""

CLAIM_SQL = """
SELECT id, payload, attempts, max_attempts FROM job_queue.jobs
WHERE status = 'queued' AND run_at <= now()
ORDER BY run_at, id
FOR UPDATE SKIP LOCKED
LIMIT 1
"""


def backoff_s(attempt: int) -> int:
    return min(2**attempt, MAX_BACKOFF_S)


def next_state(attempt: int, max_attempts: int) -> tuple[str, int]:
    """After failed attempt number `attempt`: ('queued', delay_s) to retry, or ('failed', 0)."""
    if attempt >= max_attempts:
        return "failed", 0
    return "queued", backoff_s(attempt)


def is_pooled(url: str) -> bool:
    return "-pooler." in url


def ensure_schema(conn: Any) -> None:
    conn.execute(SCHEMA_SQL)


def enqueue(conn: Any, payloads: list[dict]) -> None:
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO job_queue.jobs (payload) VALUES (%s)", [(Jsonb(p),) for p in payloads]
            )
        conn.execute(f"NOTIFY {CHANNEL}")  # delivered to listeners when this transaction commits


def run_one(conn: Any, worker: str, handler: Callable[[dict], None]) -> tuple[int, str] | None:
    """Claim one ready job, run it, record the outcome, all in one transaction.

    If the worker dies mid-job the transaction aborts, the row lock is released and the
    job is claimable again: no 'running' state to get stuck in.
    """
    with conn.transaction():
        row = conn.execute(CLAIM_SQL).fetchone()
        if row is None:
            return None
        job_id, payload, attempts, max_attempts = row
        attempt = attempts + 1
        try:
            handler(payload)
        except Exception as e:  # noqa: BLE001 - any handler failure is a job failure
            status, delay = next_state(attempt, max_attempts)
            conn.execute(
                "UPDATE job_queue.jobs SET status = %s, attempts = %s, "
                "run_at = now() + make_interval(secs => %s), last_error = %s, last_worker = %s "
                "WHERE id = %s",
                (status, attempt, delay, str(e), worker, job_id),
            )
            return job_id, "retry" if status == "queued" else "failed"
        conn.execute(
            "UPDATE job_queue.jobs SET status = 'done', attempts = %s, last_worker = %s "
            "WHERE id = %s",
            (attempt, worker, job_id),
        )
        return job_id, "done"


def queued_count(conn: Any) -> int:
    return conn.execute("SELECT count(*) FROM job_queue.jobs WHERE status = 'queued'").fetchone()[0]


def status_counts(conn: Any) -> dict[str, int]:
    rows = conn.execute("SELECT status, count(*) FROM job_queue.jobs GROUP BY status").fetchall()
    return {s: n for s, n in rows}


def ping(url: str, timeout_s: float = 5.0) -> float | None:
    """NOTIFY from one connection, LISTEN on another. Returns delivery latency in ms, or None."""
    with psycopg.connect(url, autocommit=True) as listener, \
            psycopg.connect(url, autocommit=True) as sender:
        listener.execute("LISTEN job_queue_ping")
        started = time.monotonic()
        sender.execute("SELECT pg_notify('job_queue_ping', 'ping')")
        for _ in listener.notifies(timeout=timeout_s, stop_after=1):
            return round((time.monotonic() - started) * 1000, 1)
    return None
