"""text2sql-eval CLI."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import uuid

from dotenv import load_dotenv

from text2sql_eval.cases import CaseFileError, load_cases
from text2sql_eval.keon import forked, reset_branch
from text2sql_eval.llm import DEFAULT_MODELS, KEY_ENV, complete
from text2sql_eval.output import event, output_error, output_json
from text2sql_eval.runner import SYSTEM_PROMPT, CaseResult, connect, run_eval


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="text2sql-eval",
        description="Grade an LLM's text-to-SQL on a disposable Kisenon fork.",
    )
    p.add_argument("--cases", default="cases.yaml", help="YAML case file.")
    p.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    p.add_argument("--model", default=None, help="Override the provider default model.")
    p.add_argument("--project", default=None, help="Override KISENON_PROJECT_ID.")
    p.add_argument("--keep", action="store_true", help="Keep the fork for debugging.")
    p.add_argument("--pretty", action="store_true", help="Suppress the JSON line.")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))

    project = args.project or os.environ.get("KISENON_PROJECT_ID")
    if not project:
        output_error("KISENON_PROJECT_ID is not set (and --project not given).",
                     {"hint": "Set it in .env — see README#setup"}, exit_code=2)
    key = KEY_ENV[args.provider]
    if not os.environ.get(key):
        output_error(f"{key} is not set.",
                     {"hint": "See README#bring-your-own-keys"}, exit_code=2)
    try:
        cases = load_cases(args.cases)
    except (OSError, CaseFileError) as e:
        output_error(str(e), exit_code=2)

    model = args.model or DEFAULT_MODELS[args.provider]
    name = f"text2sql-eval-{uuid.uuid4().hex[:8]}"
    event("eval start", cases=len(cases), provider=args.provider, model=model)

    def ask(question: str, schema: str) -> str:
        return complete(args.provider, model, SYSTEM_PROMPT.format(schema=schema), question)

    try:
        with forked(project=project, name=name, keep=args.keep) as (branch, url):
            event("branch forked", id=branch.id, duration_ms=branch.created_in_ms)

            def reset() -> None:
                reset_branch(branch_id=branch.id)
                event("branch reset", id=branch.id)

            results = run_eval(cases, ask=ask, connect=lambda: connect(url), reset_fork=reset)
    except Exception as e:  # noqa: BLE001 — keon/LLM/DB setup failures are fatal
        output_error(f"{type(e).__name__}: {e}", exit_code=2)

    passed = sum(1 for r in results if r.match)
    _print_table(results, passed)
    if not args.pretty:
        output_json({
            "branch": {"name": branch.name, "id": branch.id, "kept": args.keep},
            "provider": args.provider,
            "model": model,
            "passed": passed,
            "total": len(results),
            "cases": [_as_dict(r) for r in results],
        })
    return 0 if passed == len(results) else 1


def _as_dict(r: CaseResult) -> dict:
    return {
        "id": r.id, "question": r.question, "sql": r.sql, "executed": r.executed,
        "match": r.match, "reason": r.reason, "reset": r.reset, "duration_ms": r.duration_ms,
    }


def _print_table(results: list[CaseResult], passed: int) -> None:
    print(f"{'case':<28} {'exec':<5} {'match':<9} reason")
    for r in results:
        print(f"{r.id:<28} {'ok' if r.executed else 'FAIL':<5} {r.match or '-':<9} {r.reason}")
    kinds = [r.match for r in results]
    print(
        f"Score: {passed}/{len(results)} passed "
        f"(exact {kinds.count('exact')}, set {kinds.count('set')}, "
        f"rowcount {kinds.count('rowcount')}, executed {sum(r.executed for r in results)}, "
        f"resets {sum(r.reset for r in results)})"
    )


if __name__ == "__main__":
    raise SystemExit(main())
