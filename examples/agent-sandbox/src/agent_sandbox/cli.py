"""agent-sandbox CLI entry."""
from __future__ import annotations

import argparse
import os
import secrets
import time

from dotenv import load_dotenv

from agent_sandbox.loop import LoopOptions, LoopResult, run_ask
from agent_sandbox.output import event, output_error, output_json, print_answer
from agent_sandbox.providers import get_provider


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-sandbox",
        description="Hand an LLM a disposable Kisenon-fork sandbox; let it answer a question.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="Ask one question against a fresh fork.")
    ask.add_argument("--question", required=True, help="The natural-language question.")
    ask.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    ask.add_argument("--model", default=None, help="Override the provider default model.")
    ask.add_argument("--max-queries", type=int, default=10)
    ask.add_argument("--max-wall-s", type=int, default=120)
    ask.add_argument("--row-cap", type=int, default=1000)
    ask.add_argument(
        "--pretty", action="store_true",
        help="Print only the human answer (suppress the JSON line).",
    )
    ask.add_argument(
        "--always-delete", action="store_true",
        help="Delete the branch even on cap-hit / fatal (default: preserve).",
    )
    ask.add_argument("--project", default=None, help="Override KISENON_PROJECT_ID.")
    ask.add_argument("--name", default=None, help="Override the auto-generated branch name.")
    return p


def generate_branch_name() -> str:
    return f"agent-sandbox-{int(time.time())}-{secrets.token_hex(3)}"


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

    provider_env_var = "ANTHROPIC_API_KEY" if args.provider == "anthropic" else "OPENAI_API_KEY"
    if not os.environ.get(provider_env_var):
        output_error(
            f"{provider_env_var} is not set.",
            {"hint": f"Add {provider_env_var} to .env or your environment."},
            exit_code=2,
        )

    branch_name = args.name or generate_branch_name()
    opts = LoopOptions(
        question=args.question,
        provider_name=args.provider,
        model=args.model,
        max_queries=args.max_queries,
        max_wall_s=args.max_wall_s,
        row_cap=args.row_cap,
        always_delete=args.always_delete,
        project=project,
        branch_name=branch_name,
    )

    provider = get_provider(args.provider, model=args.model)
    event("ask start", question=args.question[:80], provider=args.provider, model=provider.model)
    result = run_ask(opts, provider=provider)

    print_answer(result.answer)
    if not args.pretty:
        output_json(_result_to_payload(result))

    return 0 if result.cap_hit is None else 1


def _result_to_payload(r: LoopResult) -> dict:
    return {
        "answer": r.answer,
        "branch": {
            "name": r.branch_name,
            "id": r.branch_id,
            "url": r.branch_url,
            "created_in_ms": r.branch_created_in_ms,
            "deleted": r.branch_deleted,
            "delete_skipped_reason": r.branch_delete_skipped_reason,
        },
        "queries": [
            {
                "iteration": q.iteration,
                "sql": q.sql,
                "rows_returned": q.rows_returned,
                "rows_truncated": q.rows_truncated,
                "duration_ms": q.duration_ms,
                "result_preview": q.result_preview,
                "error": q.error,
            }
            for q in r.queries
        ],
        "provider": r.provider,
        "model": r.model,
        "cap_hit": r.cap_hit,
        "total_duration_ms": r.total_duration_ms,
    }


if __name__ == "__main__":
    raise SystemExit(main())
