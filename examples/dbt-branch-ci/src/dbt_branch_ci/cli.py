"""dbt-branch-ci: run `dbt build` on a Kisenon fork of main and diff it against main.

  dbt-branch-ci baseline   build the dbt project on main (your "production" run)
  dbt-branch-ci check      fork main -> dbt build on the fork -> compare -> delete fork

stderr: progress events. stdout: comparison table + one JSON line.
Exit codes: 0 pass, 1 dbt build failed or a threshold tripped, 2 setup error.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg2
from dotenv import load_dotenv

from dbt_branch_ci import compare, keon

PROJECT_DIR = Path(__file__).resolve().parents[2] / "jaffle"


def event(msg: str) -> None:
    print(f"[{msg}]", file=sys.stderr, flush=True)


def dbt_env(url: str) -> dict[str, str]:
    """Split a Postgres URL into the env vars jaffle/profiles.yml reads."""
    parts = urlsplit(url)
    return {
        "DBT_HOST": parts.hostname or "",
        "DBT_PORT": str(parts.port or 5432),
        "DBT_USER": unquote(parts.username or ""),
        "DBT_ENV_SECRET_PASSWORD": unquote(parts.password or ""),
        "DBT_DBNAME": parts.path.lstrip("/") or "main",
    }


def run_dbt(url: str) -> int:
    """`dbt build` against the branch at `url`; dbt's own output goes to stderr."""
    dbt = Path(sys.executable).parent / "dbt"
    proc = subprocess.run(
        [str(dbt), "build", "--project-dir", str(PROJECT_DIR), "--profiles-dir", str(PROJECT_DIR)],
        env={**os.environ, **dbt_env(url)},
        stdout=sys.stderr,
        check=False,
    )
    return proc.returncode


def cmd_baseline(args: argparse.Namespace, project: str) -> int:
    url = keon.get_branch_url(project=project, branch="main")
    event("dbt build on main")
    code = run_dbt(url)
    event(f"dbt build done: exit={code}")
    return 0 if code == 0 else 1


def cmd_check(args: argparse.Namespace, project: str) -> int:
    started = time.monotonic()
    main_id = keon.find_branch_id(project=project, name="main")
    name = f"dbt-branch-ci-{uuid.uuid4().hex[:8]}"
    fork = keon.create_branch(project=project, name=name, parent_id=main_id)
    event(f"branch forked: {fork.name} | id={fork.id}")
    try:
        fork_url = keon.get_branch_url(project=project, branch=fork.name)
        event(f"dbt build on {fork.name}")
        dbt_code = run_dbt(fork_url)
        relations = compare.relations_from_manifest(PROJECT_DIR / "target" / "manifest.json")
        main_url = keon.get_branch_url(project=project, branch="main")
        with psycopg2.connect(main_url) as main_conn, psycopg2.connect(fork_url) as fork_conn:
            diffs = compare.diff(
                compare.snapshot(main_conn, relations), compare.snapshot(fork_conn, relations)
            )
        problems = compare.failures(diffs, args.max_row_delta_pct)
        if dbt_code != 0:
            problems.insert(0, f"dbt build failed (exit {dbt_code})")
        print(compare.render_table(diffs))
        for p in problems:
            print(f"FAIL {p}")
        print("PASS" if not problems else f"{len(problems)} problem(s)")
        print(json.dumps({
            "passed": not problems,
            "failures": problems,
            "branch": {"name": fork.name, "id": fork.id, "kept": args.keep},
            "max_row_delta_pct": args.max_row_delta_pct,
            "models": [
                {"name": d.name, "main_rows": d.main_rows, "fork_rows": d.fork_rows,
                 "delta_pct": d.delta_pct, "added_columns": d.added_columns,
                 "removed_columns": d.removed_columns, "changed_types": d.changed_types}
                for d in diffs
            ],
            "total_duration_ms": int((time.monotonic() - started) * 1000),
        }))
        return 0 if not problems else 1
    finally:
        if args.keep:
            event(f"branch kept: {fork.name} | delete: keon branches delete --cascade {fork.id}")
        else:
            try:
                keon.delete_branch(branch_id=fork.id)
                event(f"branch deleted: {fork.id}")
            except keon.KeonError as e:
                event(f"cleanup failed: {e} | run: keon branches delete --cascade {fork.id}")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="dbt-branch-ci")
    parser.add_argument("--project", default=os.environ.get("KISENON_PROJECT_ID"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("baseline", help="dbt build on main")
    check = sub.add_parser("check", help="dbt build on a fork of main and compare")
    check.add_argument("--max-row-delta-pct", type=float, default=10.0,
                       help="fail when any model's row count moves more than this (default 10)")
    check.add_argument("--keep", action="store_true", help="keep the fork for debugging")
    args = parser.parse_args(argv)

    if not args.project:
        print("KISENON_PROJECT_ID is not set (see README: Setup)", file=sys.stderr)
        return 2
    # SIGTERM (CI cancel) -> SystemExit so the fork cleanup in `finally` runs
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    handler = cmd_baseline if args.cmd == "baseline" else cmd_check
    try:
        return handler(args, args.project)
    except keon.KeonError as e:
        print(str(e), file=sys.stderr)
        return 2
    except psycopg2.Error as e:
        print(f"database error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
