"""index-advisor CLI: check | workload | advise."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import uuid

from dotenv import load_dotenv

from index_advisor.bench import (
    SYSTEM,
    USER,
    Result,
    benchmark,
    parse_proposals,
    rank,
    to_concurrent,
)
from index_advisor.llm import DEFAULT_MODELS, KEY_ENV, complete, extract_json
from index_advisor.output import event, output_error, output_json
from index_advisor.stats import (
    check_pgss,
    connect,
    describe_schema,
    table_stats,
    top_queries,
)
from index_advisor.workload import run_workload


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="index-advisor",
        description="pg_stat_statements -> LLM index candidates -> one Kisenon fork each.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Is pg_stat_statements usable on main?")
    w = sub.add_parser("workload", help="Run the demo read workload on main.")
    w.add_argument("--rounds", type=int, default=50)
    a = sub.add_parser("advise", help="Propose + benchmark indexes.")
    a.add_argument("--match", default="%", help="ILIKE filter on statement text.")
    a.add_argument("--top", type=int, default=5, help="Statements to consider.")
    a.add_argument("--max-candidates", type=int, default=5)
    a.add_argument("--provider", choices=["anthropic", "openai"], default="anthropic")
    a.add_argument("--model", default=None)
    a.add_argument("--project", default=None, help="Override KISENON_PROJECT_ID.")
    a.add_argument("--keep", action="store_true", help="Keep every candidate fork.")
    a.add_argument("--pretty", action="store_true", help="Suppress the JSON line.")
    return p


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        output_error(f"{name} is not set.", {"hint": "See README#bring-your-own-keys"}, exit_code=2)
    return value


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    main_url = _require("KISENON_URL")

    if args.command == "workload":
        conn = connect(main_url)
        try:
            n = run_workload(conn, rounds=args.rounds)
        finally:
            conn.close()
        print(f"Ran {n} statements on main. Next: uv run index-advisor advise")
        output_json({"statements": n})
        return 0

    project = ""
    if args.command == "advise":
        project = args.project or _require("KISENON_PROJECT_ID")
        _require(KEY_ENV[args.provider])

    conn = connect(main_url)
    try:
        problem = check_pgss(conn)
        if problem:
            output_error(problem, exit_code=2)
        if args.command == "check":
            n = len(top_queries(conn, match="%", limit=1000))
            print(f"pg_stat_statements: ok ({n} SELECT statements recorded in this database)")
            output_json({"pg_stat_statements": "ok", "statements": n})
            return 0
        tops = top_queries(conn, match=args.match, limit=args.top)
        if not tops:
            output_error(
                f"no SELECT statements matching {args.match!r} in pg_stat_statements.",
                {"hint": "Run `uv run index-advisor workload` first (stats reset when the "
                         "compute restarts)."},
                exit_code=2,
            )
        stats = table_stats(conn)
        schema_text = describe_schema(conn, stats)
    finally:
        conn.close()

    model = args.model or DEFAULT_MODELS[args.provider]
    event("advise start", statements=len(tops), model=model)
    tops_text = "\n".join(
        f"queryid={t.queryid} calls={t.calls} mean_ms={t.mean_ms:.2f}\n  {t.query}" for t in tops
    )
    try:
        proposals = parse_proposals(extract_json(complete(
            args.provider, model, SYSTEM.format(n=args.max_candidates),
            USER.format(schema=schema_text, tops=tops_text),
        )), max_n=args.max_candidates)
    except Exception as e:  # noqa: BLE001 — LLM/provider failure is fatal
        output_error(f"{type(e).__name__}: {e}", exit_code=2)

    calls = {t.queryid: t.calls for t in tops}
    run_id = uuid.uuid4().hex[:8]
    results = rank([
        benchmark(p, project=project, name=f"index-advisor-{run_id}-{i}", keep=args.keep,
                  stats=stats, calls=calls.get(p.queryid, 0))
        for i, p in enumerate(proposals, start=1)
    ])
    _print(results)
    if not args.pretty:
        output_json({"model": model, "provider": args.provider,
                     "recommendations": [_as_dict(r) for r in results]})
    return 0 if any(r.est_saved_ms > 0 for r in results) else 1


def _as_dict(r: Result) -> dict:
    return {
        "index_sql": to_concurrent(r.proposal.index_sql) + ";",
        "table": r.proposal.table, "queryid": r.proposal.queryid,
        "sample_query": r.proposal.sample_query, "why": r.proposal.why,
        "before_ms": r.before_ms, "after_ms": r.after_ms, "used": r.used,
        "index_bytes": r.index_bytes, "calls": r.calls, "est_saved_ms": r.est_saved_ms,
        "write_overhead": r.write_note, "branch": r.branch, "error": r.error,
    }


def _print(results: list[Result]) -> None:
    if not results:
        print("No usable index candidates.")
        return
    for i, r in enumerate(results, start=1):
        if r.error:
            print(f"{i}. FAILED {r.proposal.index_sql}\n   {r.error}")
            continue
        verdict = "recommended" if r.est_saved_ms > 0 else "not used by the planner / no gain"
        print(f"{i}. {verdict}: {r.before_ms:.2f} ms -> {r.after_ms:.2f} ms per call, "
              f"{r.calls} calls, ~{r.est_saved_ms:.0f} ms saved; "
              f"size {r.index_bytes / 1024 / 1024:.1f} MB")
        print(f"   {to_concurrent(r.proposal.index_sql)};")
        print(f"   why: {r.proposal.why}")
        print(f"   write overhead: {r.write_note}")


if __name__ == "__main__":
    raise SystemExit(main())
