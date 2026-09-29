"""parallel-agents CLI."""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from parallel_agents.keon import Branch, KeonError, delete_branch
from parallel_agents.llm import DEFAULT_MODELS, KEY_ENV, complete
from parallel_agents.output import event, output_error, output_json
from parallel_agents.race import STRATEGIES, Candidate, pick_winner, race


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="parallel-agents",
        description="LLM agents race to speed up one query, each on its own Kisenon fork.",
    )
    p.add_argument("--query-file", default="dashboard.sql", help="SQL file with the slow query.")
    p.add_argument("--goal-ms", type=float, default=5.0, help="Target execution time.")
    p.add_argument("--strategies", default="index,rewrite,matview",
                   help=f"Comma list, one agent each. Known: {','.join(STRATEGIES)}.")
    p.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    p.add_argument("--model", default=None)
    p.add_argument("--project", default=None, help="Override KISENON_PROJECT_ID.")
    p.add_argument("--keep", action="store_true", help="Keep the winner's fork (losers always go).")
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
        output_error(f"{key} is not set.", {"hint": "See README#bring-your-own-keys"}, exit_code=2)
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    unknown = [s for s in strategies if s not in STRATEGIES]
    if unknown or not strategies:
        output_error(f"unknown strategy: {', '.join(unknown) or '(none given)'}",
                     {"known": sorted(STRATEGIES)}, exit_code=2)
    try:
        query = Path(args.query_file).read_text().strip().rstrip(";")
    except OSError as e:
        output_error(str(e), exit_code=2)

    model = args.model or DEFAULT_MODELS[args.provider]
    run_id = uuid.uuid4().hex[:8]
    event("race start", agents=len(strategies), goal_ms=args.goal_ms, model=model)

    def ask(system: str, user: str) -> str:
        return complete(args.provider, model, system, user)

    created: list[Branch] = []
    candidates: list[Candidate] = []
    winner: Candidate | None = None
    try:
        candidates = asyncio.run(race(strategies, project=project, run_id=run_id, query=query,
                                      goal_ms=args.goal_ms, ask=ask, created=created))
        winner = pick_winner(candidates)
    finally:
        for b in created:
            if args.keep and winner is not None and winner.branch is b:
                event("branch kept", id=b.id, name=b.name)
                continue
            try:
                delete_branch(branch_id=b.id)
                event("branch deleted", id=b.id)
            except KeonError as e:
                event("cleanup failed", id=b.id, error=e,
                      run=f"keon branches delete --cascade {b.id}")

    if all(c.branch is None for c in candidates):
        output_error(candidates[0].error if candidates else "no candidates ran", exit_code=2)

    met = winner is not None and winner.after_ms <= args.goal_ms
    _print_report(candidates, winner, args.goal_ms, met)
    if not args.pretty:
        output_json({
            "goal_ms": args.goal_ms,
            "winner": winner.strategy if winner else None,
            "met_goal": met,
            "kept_branch": winner.branch.name if (args.keep and winner) else None,
            "provider": args.provider,
            "model": model,
            "candidates": [_as_dict(c) for c in candidates],
        })
    return 0 if met else 1


def _as_dict(c: Candidate) -> dict:
    return {
        "strategy": c.strategy,
        "branch": {"name": c.branch.name, "id": c.branch.id} if c.branch else None,
        "correct": c.correct, "baseline_ms": c.baseline_ms, "after_ms": c.after_ms,
        "setup_sql": c.setup_sql, "query": c.query, "rationale": c.rationale, "error": c.error,
    }


def _print_report(cands: list[Candidate], winner: Candidate | None, goal: float, met: bool) -> None:
    print(f"{'strategy':<10} {'correct':<8} {'before_ms':>10} {'after_ms':>10}  note")
    for c in cands:
        before = f"{c.baseline_ms:.2f}" if c.baseline_ms is not None else "-"
        after = f"{c.after_ms:.2f}" if c.after_ms is not None else "-"
        note = c.error or c.rationale
        print(f"{c.strategy:<10} {'yes' if c.correct else 'no':<8} {before:>10} {after:>10}  {note}")
    if winner is None:
        print("Winner: none (no candidate returned identical rows)")
        return
    print(f"Winner: {winner.strategy} — {winner.after_ms:.2f} ms "
          f"(goal {goal:g} ms: {'met' if met else 'missed'})")
    for stmt in winner.setup_sql:
        print(f"  {stmt}")
    if winner.query:
        print(f"  -- query: {' '.join(winner.query.split())}")


if __name__ == "__main__":
    raise SystemExit(main())
