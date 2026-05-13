"""branch-test CLI entry."""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import time

from dotenv import load_dotenv

from branch_test.output import output_error, output_json, output_pretty
from branch_test.run import (
    RunOptions,
    execute_run,
    render_pretty,
    result_as_dict,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="branch-test",
        description="Fork a Kisenon main branch, run a migration, report JSON.",
    )
    p.add_argument("--migrate", required=True, help="The migration command to run.")
    p.add_argument("--verify", default=None, help="Optional verify command (tests/smoke).")
    p.add_argument("--rollback", default=None, help="Optional rollback command.")
    p.add_argument("--project", default=None, help="Override KISENON_PROJECT_ID.")
    p.add_argument("--name", default=None, help="Override the auto-generated branch name.")
    p.add_argument("--keep", action="store_true", help="Keep branch even on green.")
    p.add_argument("--delete", action="store_true", help="Always delete branch, even on red.")
    p.add_argument("--pretty", action="store_true", help="Human-readable stdout.")
    p.add_argument("--timeout-s", type=int, default=600, help="Per-step timeout seconds.")
    p.add_argument("--working-dir", default=".", help="cd into here for subcommands.")
    p.add_argument("--no-schema-diff", action="store_true",
                   help="Skip pg_dump capture (saves ~1s per run).")
    return p


def generate_branch_name() -> str:
    return f"branch-test-{int(time.time())}-{secrets.token_hex(3)}"


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()

    project = args.project or os.environ.get("KISENON_PROJECT_ID")
    if not project:
        output_error(
            "KISENON_PROJECT_ID is not set (and --project not given).",
            {"hint": "Set in .env or pass --project <id>"},
            exit_code=2,
        )

    main_url = os.environ.get("KISENON_URL", "")
    if not main_url:
        # Not fatal -- promote_hint just shows a placeholder.
        main_url = "<set KISENON_URL to your main branch URI>"

    branch_name = args.name or generate_branch_name()

    opts = RunOptions(
        migrate_cmd=args.migrate,
        verify_cmd=args.verify,
        rollback_cmd=args.rollback,
        working_dir=args.working_dir,
        timeout_s=args.timeout_s,
        schema_diff=not args.no_schema_diff,
        branch_name=branch_name,
        keep=args.keep,
        delete=args.delete,
    )

    if args.pretty:
        # Pretty progress: announce branch creation early so a human sees it.
        sys.stderr.write(f"creating branch {branch_name} ...\n")
        sys.stderr.flush()

    result, exit_code = execute_run(
        opts, project=project, main_url=main_url, branch_name=branch_name,
    )

    payload = result_as_dict(result)
    if args.pretty:
        output_pretty(result, render_pretty)
    else:
        output_json(payload)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
