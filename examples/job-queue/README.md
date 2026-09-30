# job-queue

A background-job queue in plain Postgres:

- `SELECT ... FOR UPDATE SKIP LOCKED` so N workers claim different jobs without blocking
- retries with exponential backoff (2 s, 4 s, 8 s, then `failed`)
- `LISTEN/NOTIFY` wakeups so idle workers react immediately, with polling as the safety net

## What you need

- A Kisenon project (`keon login`), Python 3.11+, [uv](https://docs.astral.sh/uv/).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `DATABASE_URL` | `keon connection-string main --project <id>` (**not** `--pooled`) | required | exits 2 |

No API keys needed.

## Setup

```bash
cd examples/job-queue
uv sync
cp .env.example .env   # set DATABASE_URL (direct URI)
uv run job-queue ping
```
```
NOTIFY delivered in 40.4 ms
{"notify_delivered": true, "latency_ms": 40.4}
```

## Demo

```bash
uv run job-queue demo --jobs 40 --workers 4 --fail-rate 0.2
```

This starts 4 workers. They `LISTEN` on an empty queue, then 40 jobs are enqueued in one
transaction with a `NOTIFY`, and the workers wake up, share the work, and retry failures:

```
[enqueued: 40 | notify=job_queue]
[job: 4 | worker=w4 | outcome=done]
[job: 1 | worker=w2 | outcome=done]
...
[job: 9 | worker=w4 | outcome=retry]
...
[job: 22 | worker=w2 | outcome=done]
[job: 33 | worker=w2 | outcome=done]
done=40 retries=12 failed=0 wakeups=4 workers=4 in 14843 ms
{"done": 40, "retries": 12, "failed": 0, "notify_wakeups": 4, "workers": 4, "by_status": {"done": 40}, "duration_ms": 14843}
```

`notify_wakeups >= 1` shows NOTIFY was delivered through the Kisenon proxy. The run takes a
few seconds longer than the work itself because retried jobs wait out their backoff.

Two terminals instead:

```bash
uv run job-queue work --workers 4 --idle-s 30     # terminal 1: waits on LISTEN
uv run job-queue enqueue --jobs 20                # terminal 2: workers wake on the NOTIFY
```

Crash safety: press Ctrl-C during `demo`. Jobs that were mid-flight roll back to `queued`,
and the next `work` picks them up.

## Pooling and LISTEN/NOTIFY

`LISTEN` belongs to a **session**. A transaction-mode pooler (PgBouncer) hands your session
to someone else after each transaction, so notifications can be lost. Use the direct
URI for workers. The `-pooler.` URI is fine for code that only enqueues, but the `NOTIFY`
itself is harmless either way.

Measured on Kisenon: with the direct URI `ping` delivers in ~40 ms. With the `--pooled` URI
it does not deliver:

```
[warning: DATABASE_URL is a pooled URI; LISTEN/NOTIFY needs the direct one]
NOTIFY was not delivered within 5 s. If DATABASE_URL is the pooled URI (host contains '-pooler.'), switch to the direct one: ...
{"notify_delivered": false}
```

If `ping` fails in your environment, the queue still works: every worker re-checks the table
every `--poll-s` seconds, so NOTIFY only reduces latency and isn't needed for correctness.

## How it works

`src/job_queue/queue.py` is ~100 lines. Each job is claimed, run and recorded inside
**one transaction**. If a worker dies, Postgres releases the row lock and the job is
claimable again, so there is no "stuck running" state and no reaper.

## Limitations

- A job holds a transaction (and a connection) while it runs. For jobs that take minutes,
  switch to a lease: `status='running', locked_until=now()+interval` committed at claim, plus
  a sweep for expired leases.
- No priorities or per-queue concurrency limits; add columns to the `ORDER BY` / `WHERE`.
