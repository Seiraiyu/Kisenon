"""job-queue CLI: N workers on a Postgres queue, woken by LISTEN/NOTIFY."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from collections import Counter

import psycopg
from dotenv import load_dotenv

from job_queue import queue

FALLBACK = (
    "NOTIFY was not delivered within 5 s. If DATABASE_URL is the pooled URI (host contains "
    "'-pooler.'), switch to the direct one: `keon connection-string main --project <id>` "
    "(without --pooled). If it still fails, the workers remain correct with polling alone: "
    "run them with a smaller --poll-s (e.g. --poll-s 0.5); NOTIFY only reduces latency."
)


def event(label: str, **fields) -> None:
    items = list(fields.items())
    body = " | ".join([str(items[0][1])] + [f"{k}={v}" for k, v in items[1:]]) if items else ""
    sys.stderr.write(f"[{label}: {body}]\n" if body else f"[{label}]\n")
    sys.stderr.flush()


def build_parser() -> argparse.ArgumentParser:
    workers = argparse.ArgumentParser(add_help=False)
    workers.add_argument("--workers", type=int, default=4)
    workers.add_argument("--idle-s", type=float, default=3.0,
                         help="Exit once the queue is empty and no job ran for this long.")
    workers.add_argument("--poll-s", type=float, default=1.0,
                         help="Max wait for a NOTIFY before re-checking the table.")
    jobs = argparse.ArgumentParser(add_help=False)
    jobs.add_argument("--jobs", type=int, default=40)
    jobs.add_argument("--fail-rate", type=float, default=0.2)
    jobs.add_argument("--work-ms", type=int, default=200)

    p = argparse.ArgumentParser(prog="job-queue", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", parents=[workers, jobs],
                   help="Truncate, start workers, enqueue jobs, run until done.")
    sub.add_parser("enqueue", parents=[jobs], help="Add jobs and NOTIFY.")
    sub.add_parser("work", parents=[workers], help="Run workers until the queue drains.")
    sub.add_parser("ping", help="Check that NOTIFY reaches a LISTENing session.")
    return p


def worker_loop(url: str, name: str, args, stats: Counter, lock: threading.Lock) -> None:
    rng = random.Random()

    def handler(payload: dict) -> None:
        time.sleep(payload.get("work_ms", 100) / 1000)
        if rng.random() < payload.get("fail_rate", 0.0):
            raise RuntimeError("simulated failure")

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"LISTEN {queue.CHANNEL}")
        last_active = time.monotonic()
        while True:
            got = queue.run_one(conn, name, handler)
            if got:
                job_id, outcome = got
                with lock:
                    stats[outcome] += 1
                event("job", id=job_id, worker=name, outcome=outcome)
                last_active = time.monotonic()
                continue
            if queue.queued_count(conn) == 0 and time.monotonic() - last_active >= args.idle_s:
                return
            for _ in conn.notifies(timeout=args.poll_s, stop_after=1):
                with lock:
                    stats["wakeups"] += 1


def _payloads(args) -> list[dict]:
    return [
        {"n": i, "work_ms": args.work_ms, "fail_rate": args.fail_rate} for i in range(args.jobs)
    ]


def run_workers(url: str, args, *, enqueue_after_start: bool) -> int:
    stats: Counter = Counter()
    lock = threading.Lock()
    started = time.monotonic()
    threads = [
        threading.Thread(
            target=worker_loop, args=(url, f"w{i + 1}", args, stats, lock), daemon=True
        )
        for i in range(args.workers)
    ]
    for t in threads:
        t.start()
    if enqueue_after_start:
        time.sleep(1.0)  # workers are now LISTENing on an empty queue
        with psycopg.connect(url, autocommit=True) as conn:
            queue.enqueue(conn, _payloads(args))
        event("enqueued", jobs=args.jobs, notify=queue.CHANNEL)
    for t in threads:
        t.join()
    with psycopg.connect(url, autocommit=True) as conn:
        by_status = queue.status_counts(conn)
    ms = int((time.monotonic() - started) * 1000)
    print(f"done={stats['done']} retries={stats['retry']} failed={stats['failed']} "
          f"wakeups={stats['wakeups']} workers={args.workers} in {ms} ms")
    print(json.dumps({"done": stats["done"], "retries": stats["retry"], "failed": stats["failed"],
                      "notify_wakeups": stats["wakeups"], "workers": args.workers,
                      "by_status": by_status, "duration_ms": ms}))
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    if not url:
        err = {"error": "DATABASE_URL is not set.", "hint": "README#setup"}
        sys.stderr.write(json.dumps(err) + "\n")
        sys.exit(2)
    if queue.is_pooled(url):
        event("warning", msg="DATABASE_URL is a pooled URI; LISTEN/NOTIFY needs the direct one")

    if args.command == "ping":
        latency = queue.ping(url)
        if latency is None:
            sys.stderr.write(FALLBACK + "\n")
            print(json.dumps({"notify_delivered": False}))
            return 2
        print(f"NOTIFY delivered in {latency} ms")
        print(json.dumps({"notify_delivered": True, "latency_ms": latency}))
        return 0

    with psycopg.connect(url, autocommit=True) as conn:
        queue.ensure_schema(conn)
        if args.command == "demo":
            conn.execute("TRUNCATE job_queue.jobs")
        if args.command == "enqueue":
            queue.enqueue(conn, _payloads(args))
            print(f"Enqueued {args.jobs} jobs")
            print(json.dumps({"enqueued": args.jobs}))
            return 0
    return run_workers(url, args, enqueue_after_start=args.command == "demo")


if __name__ == "__main__":
    raise SystemExit(main())
