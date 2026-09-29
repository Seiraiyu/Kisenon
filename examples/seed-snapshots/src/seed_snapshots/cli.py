"""seed-snapshots: build named fixture branches once, then fork/reset instead of re-seeding.

  seed-snapshots build [--fixture NAME ...] [--rebuild]
  seed-snapshots timing [--fixture NAME] [--runs N]

stderr: progress events. stdout: human summary + one JSON line.
Exit codes: 0 ok, 1 a timing run failed, 2 setup error (env, keon, missing fixture).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import sys
import time
import uuid

import psycopg
from dotenv import load_dotenv

from seed_snapshots import keon
from seed_snapshots.seed import FIXTURES, seed


def event(msg: str) -> None:
    print(f"[{msg}]", file=sys.stderr, flush=True)


def ms_since(t: float) -> int:
    return int((time.monotonic() - t) * 1000)


def fork_name() -> str:
    return f"seed-snapshots-{uuid.uuid4().hex[:8]}"


def count_orders(url: str) -> int:
    """Connect and read the fixture: 'ready' means the data is queryable."""
    with psycopg.connect(url) as conn:
        return conn.execute("SELECT count(*) FROM seed_snapshots.orders").fetchone()[0]


def cmd_build(args: argparse.Namespace, project: str) -> int:
    ids = keon.branch_ids(project=project)
    built = []
    for fixture in args.fixture or list(FIXTURES):
        name = f"fixture-{fixture}"
        if name in ids and not args.rebuild:
            event(f"exists: {name} | id={ids[name]} (use --rebuild to re-seed)")
            continue
        if name in ids:
            keon.delete_branch(branch_id=ids[name])
            event(f"deleted old {name}")
        branch = keon.create_branch(project=project, name=name, parent_id=ids["main"])
        t = time.monotonic()
        with psycopg.connect(keon.get_branch_url(project=project, branch=name)) as conn:
            seed(conn, fixture)
        seed_ms = ms_since(t)
        event(f"built {name}: {seed_ms}ms | id={branch.id}")
        built.append({"fixture": fixture, "branch": name, "id": branch.id, "seed_ms": seed_ms})
    print(f"built {len(built)} fixture branch(es)")
    print(json.dumps({"built": built}))
    return 0


def cmd_timing(args: argparse.Namespace, project: str) -> int:
    ids = keon.branch_ids(project=project)
    fixture_branch = f"fixture-{args.fixture}"
    if fixture_branch not in ids:
        print(f"{fixture_branch} not found; run `seed-snapshots build` first", file=sys.stderr)
        return 2
    created: list[str] = []

    def make(parent_id: str) -> keon.Branch:
        b = keon.create_branch(project=project, name=fork_name(), parent_id=parent_id)
        created.append(b.id)
        return b

    times: dict[str, list[int]] = {"reseed": [], "fork": [], "reset": []}
    try:
        scratch = make(ids["main"])
        scratch_url = keon.get_branch_url(project=project, branch=scratch.name)
        for i in range(args.runs):
            t = time.monotonic()
            with psycopg.connect(scratch_url) as conn:
                seed(conn, args.fixture)
            times["reseed"].append(ms_since(t))
            event(f"reseed run {i + 1}: {times['reseed'][-1]}ms")

        for i in range(args.runs):
            t = time.monotonic()
            b = make(ids[fixture_branch])
            count_orders(keon.get_branch_url(project=project, branch=b.name))
            times["fork"].append(ms_since(t))
            event(f"fork run {i + 1}: {times['fork'][-1]}ms")
            keon.delete_branch(branch_id=b.id)
            created.remove(b.id)

        b = make(ids[fixture_branch])
        count_orders(keon.get_branch_url(project=project, branch=b.name))
        for i in range(args.runs):
            t = time.monotonic()
            keon.reset_branch(branch_id=b.id)
            count_orders(keon.get_branch_url(project=project, branch=b.name))
            times["reset"].append(ms_since(t))
            event(f"reset run {i + 1}: {times['reset'][-1]}ms")
    finally:
        for branch_id in created:
            try:
                keon.delete_branch(branch_id=branch_id)
                event(f"branch deleted: {branch_id}")
            except keon.KeonError as e:
                event(f"cleanup failed: {e} | run: keon branches delete --cascade {branch_id}")

    labels = {"reseed": "re-seed (SQL)", "fork": "fork fixture branch",
              "reset": "reset fork to fixture"}
    medians = {k: int(statistics.median(v)) for k, v in times.items()}
    print(f"fixture={args.fixture} runs={args.runs}")
    print(f"{'method':<24}{'p50_ms':>8}  runs_ms")
    for key, label in labels.items():
        print(f"{label:<24}{medians[key]:>8}  {times[key]}")
    print(json.dumps({"fixture": args.fixture, "runs": args.runs,
                      "p50_ms": medians, "runs_ms": times}))
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="seed-snapshots")
    parser.add_argument("--project", default=os.environ.get("KISENON_PROJECT_ID"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build", help="create + seed fixture-<name> branches from main")
    build.add_argument("--fixture", action="append", choices=list(FIXTURES),
                       help="repeatable; default: all")
    build.add_argument("--rebuild", action="store_true", help="delete and re-seed existing ones")
    timing = sub.add_parser("timing", help="re-seed vs fork vs reset, median of N runs")
    timing.add_argument("--fixture", choices=list(FIXTURES), default="prodlike")
    timing.add_argument("--runs", type=int, default=3)
    args = parser.parse_args(argv)

    if not args.project:
        print("KISENON_PROJECT_ID is not set (see README: Setup)", file=sys.stderr)
        return 2
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # run cleanup `finally`s
    handler = cmd_build if args.cmd == "build" else cmd_timing
    try:
        return handler(args, args.project)
    except keon.KeonError as e:
        print(str(e), file=sys.stderr)
        return 2
    except psycopg.Error as e:
        print(f"database error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
