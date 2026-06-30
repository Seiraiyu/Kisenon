"""agent-migrate CLI entry."""
from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from agent_migrate import keon
from agent_migrate.loop import LoopOptions, LoopResult, run_ask
from agent_migrate.output import event, output_error, output_json, print_answer
from agent_migrate.providers import get_provider


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-migrate",
        description=(
            "An LLM authors a migration, verifies it on a scoped keon sandbox, "
            "and promotes on confirmation."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="Author + verify a migration for one request.")
    ask.add_argument("--request", required=True, help="The plain-English schema change to make.")
    ask.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    ask.add_argument("--model", default=None, help="Override the provider default model.")
    ask.add_argument("--parent", default="main", help="Branch to fork the sandbox from.")
    ask.add_argument("--project", default=None, help="Override KISENON_PROJECT_ID.")
    ask.add_argument("--max-attempts", type=int, default=5, help="Max run_migration attempts.")
    ask.add_argument("--timeout-s", type=int, default=300,
                     help="Per-command timeout in the sandbox.")
    ask.add_argument("--auto-promote", action="store_true",
                     help="On green, call `keon sandbox promote` automatically "
                          "(still subject to a human-mode gate).")
    ask.add_argument("--pretty", action="store_true",
                     help="Print only the human answer (suppress JSON).")
    return p


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()

    project = args.project or os.environ.get("KISENON_PROJECT_ID")
    if not project:
        output_error("KISENON_PROJECT_ID is not set (and --project not given).",
                     {"hint": "Set in .env or pass --project <id>"}, exit_code=2)

    kisenon_url = os.environ.get("KISENON_URL")
    if not kisenon_url:
        output_error("KISENON_URL is not set.",
                     {"hint": "Needed for read-only schema introspection of main. Add it to .env."},
                     exit_code=2)

    provider_env = "ANTHROPIC_API_KEY" if args.provider == "anthropic" else "OPENAI_API_KEY"
    if not os.environ.get(provider_env):
        output_error(f"{provider_env} is not set.",
                     {"hint": f"Add {provider_env} to .env or your environment."}, exit_code=2)

    # `keon sandbox run --parent` wants a branch id; let users pass a name.
    try:
        parent_id = keon.resolve_branch_id(project=project, name=args.parent)
    except keon.KeonNotFound as e:
        output_error(str(e), exit_code=2)
    except keon.KeonError as e:
        output_error(str(e), {"hint": f"Check that branch {args.parent!r} exists in the project."},
                     exit_code=2)

    opts = LoopOptions(
        request=args.request, provider_name=args.provider, model=args.model,
        project=project, parent=parent_id, kisenon_url=kisenon_url,
        max_attempts=args.max_attempts, timeout_s=args.timeout_s, auto_promote=args.auto_promote,
    )
    provider = get_provider(args.provider, model=args.model)
    event("ask start", request=args.request[:80], provider=args.provider, model=provider.model)

    try:
        result = run_ask(opts, provider=provider)
    except keon.SandboxUnavailable as e:
        output_error(str(e),
                     {"hint": "Run a sandbox-enabled keon build against an enabled region."},
                     exit_code=2)
    except keon.KeonNotFound as e:
        output_error(str(e), exit_code=2)

    print_answer(result.answer)
    if not args.pretty:
        output_json(_payload(result))
    return 0 if result.final_status == "green" else 1


def _payload(r: LoopResult) -> dict:
    return {
        "answer": r.answer,
        "final_status": r.final_status,
        "green_sandbox_id": r.green_sandbox_id,
        "promote_hint": r.promote_hint,
        "promoted": r.promoted,
        "promote_preview": r.promote_preview,
        "attempts": [
            {"attempt": a.attempt, "status": a.status, "sandbox_id": a.sandbox_id,
             "migration_sql": a.migration_sql, "verify_sql": a.verify_sql,
             "failing_step": a.failing_step, "stderr_tail": a.stderr_tail}
            for a in r.attempts
        ],
        "provider": r.provider,
        "model": r.model,
        "total_duration_ms": r.total_duration_ms,
    }


if __name__ == "__main__":
    raise SystemExit(main())
