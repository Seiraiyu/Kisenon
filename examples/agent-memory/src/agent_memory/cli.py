"""agent-memory CLI: long-term memory for an LLM agent, stored in Kisenon Postgres."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import uuid
from dataclasses import asdict
from typing import Any

from dotenv import load_dotenv

from agent_memory import keon, llm, store
from agent_memory.embed import EmbedderError, get_embedder
from agent_memory.output import event, output_error, output_json


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--embedder", choices=["fastembed", "voyage"], default="fastembed")
    common.add_argument(
        "--reset", action="store_true", help="Drop and recreate the agent_memory schema first."
    )
    p = argparse.ArgumentParser(
        prog="agent-memory", description="Long-term memory for an LLM agent, in Postgres."
    )
    sub = p.add_subparsers(dest="command", required=True)
    say = sub.add_parser("say", parents=[common], help="Send one or more user messages, in order.")
    say.add_argument("messages", nargs="+")
    say.add_argument("--session", default="default")
    say.add_argument("--model", default=llm.DEFAULT_MODEL)
    say.add_argument(
        "--what-if", action="store_true",
        help="Run on a throwaway fork of main; memories written there are discarded.",
    )
    say.add_argument("--keep", action="store_true", help="With --what-if: keep the fork.")
    say.add_argument("--project", default=None, help="Override KISENON_PROJECT_ID.")
    rec = sub.add_parser("recall", parents=[common], help="Show the facts recalled for a query.")
    rec.add_argument("query")
    rec.add_argument("--k", type=int, default=5)
    return p


def _prepare(conn: Any, embedder: Any, reset: bool) -> None:
    try:
        store.ensure_schema(conn, embedder.dim, reset=reset)
    except store.DimMismatch as e:
        output_error(str(e), exit_code=2)


def converse(conn: Any, embedder: Any, client: Any, args: argparse.Namespace) -> list[dict]:
    turns = []
    for message in args.messages:
        facts = store.recall(conn, embedder.embed([message], query=True)[0])
        event("recall", facts=len(facts))
        history = store.recent_turns(conn, args.session)
        episode_id = store.add_episode(conn, args.session, "user", message)
        if client is None:
            answer = "Recalled: " + ("; ".join(f.content for f in facts) or "nothing yet")
            new_facts = [message]
        else:
            answer = llm.reply(client, args.model, message, [f.content for f in facts], history)
            new_facts = llm.extract_facts(client, args.model, message)
        store.add_episode(conn, args.session, "assistant", answer)
        added, merged = [], []
        vectors = embedder.embed(new_facts) if new_facts else []
        for text, vec in zip(new_facts, vectors, strict=True):
            outcome = store.upsert_fact(conn, text, vec, episode_id)
            (added if outcome == "added" else merged).append(text)
            event(f"fact {outcome}", text=text[:80])
        print(f"You: {message}\nAssistant: {answer}", flush=True)
        turns.append({
            "user": message, "assistant": answer,
            "facts_used": [asdict(f) for f in facts],
            "facts_added": added, "facts_merged": merged,
        })
    return turns


def _run_on_fork(args: argparse.Namespace, embedder: Any, client: Any) -> tuple[list, dict]:
    project = args.project or os.environ.get("KISENON_PROJECT_ID")
    if not project:
        output_error(
            "KISENON_PROJECT_ID is not set (needed for --what-if).",
            {"hint": "README#setup"}, exit_code=2,
        )
    name = f"agent-memory-{uuid.uuid4().hex[:8]}"
    try:
        branch_id = keon.create_branch(project=project, name=name)
    except keon.KeonError as e:
        output_error(str(e), exit_code=2)
    event("fork created", name=name, id=branch_id)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # SystemExit -> finally still runs
    deleted = False
    try:
        with store.connect(keon.get_branch_url(project=project, branch=name)) as conn:
            _prepare(conn, embedder, False)
            turns = converse(conn, embedder, client, args)
    finally:
        if args.keep:
            event("fork kept", name=name, cleanup=f"keon branches delete --cascade {branch_id}")
        else:
            try:
                keon.delete_branch(branch_id=branch_id)
                deleted = True
                event("fork deleted", id=branch_id)
            except keon.KeonError:
                event("fork delete FAILED", run=f"keon branches delete --cascade {branch_id}")
    return turns, {"branch": name, "id": branch_id, "deleted": deleted}


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    if not url:
        output_error("DATABASE_URL is not set.", {"hint": "README#setup"}, exit_code=2)
    if getattr(args, "what_if", False) and args.reset:
        output_error("--reset can't be combined with --what-if (it would wipe main).", exit_code=2)
    try:
        embedder = get_embedder(args.embedder)
    except EmbedderError as e:
        output_error(str(e), {"hint": "README#bring-your-own-keys"}, exit_code=2)

    if args.command == "recall":
        with store.connect(url) as conn:
            _prepare(conn, embedder, args.reset)
            facts = store.recall(conn, embedder.embed([args.query], query=True)[0], k=args.k)
        for f in facts:
            print(f"{f.score:.3f}  (sim {f.similarity:.3f}, recency {f.recency:.2f})  {f.content}")
        output_json({"query": args.query, "facts": [asdict(f) for f in facts],
                     "embedder": embedder.name})
        return 0

    client = llm.make_client()
    if client is None:
        event("no ANTHROPIC_API_KEY", mode="key-free: user messages stored verbatim as facts")
    with store.connect(url) as conn:
        _prepare(conn, embedder, args.reset)
        before = store.fact_count(conn)
        if not args.what_if:
            turns = converse(conn, embedder, client, args)
            output_json(_payload(args, embedder, client, turns, None))
            return 0
    turns, what_if = _run_on_fork(args, embedder, client)
    with store.connect(url) as conn:
        what_if |= {"main_facts_before": before, "main_facts_after": store.fact_count(conn)}
    output_json(_payload(args, embedder, client, turns, what_if))
    return 0


def _payload(args, embedder, client, turns, what_if) -> dict:
    return {
        "session": args.session, "turns": turns, "what_if": what_if,
        "embedder": embedder.name, "model": args.model if client else None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
