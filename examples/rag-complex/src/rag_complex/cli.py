"""rag-complex CLI: ingest | search | ask | experiment.

stderr: `[event: ...]` progress. stdout: human output, then one JSON line.
Exit codes: 0 ok, 1 nothing found, 2 fatal setup error.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from rag_complex import keon
from rag_complex.chunker import CHUNKERS
from rag_complex.embed import EMBEDDERS, KEY_FOR, get_embedder
from rag_complex.evaluate import format_table, load_questions, run_eval
from rag_complex.meili import Meili, index_name
from rag_complex.pipeline import event, ingest
from rag_complex.search import search, voyage_reranker
from rag_complex.store import IndexMismatch, read_meta

MODEL = "claude-sonnet-5"


class SetupError(RuntimeError):
    """Missing env/service/index: exit 2."""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rag-complex", description="Hybrid RAG on Kisenon.")
    sub = p.add_subparsers(dest="command", required=True)

    ing = sub.add_parser("ingest", help="Index corpus/parsed into main (Postgres + Meili).")
    ing.add_argument("--parsed-dir", type=Path, default=Path("corpus/parsed"))
    ing.add_argument("--pdf-dir", type=Path, default=Path("corpus/pdfs"))
    ing.add_argument("--reset", action="store_true", help="Drop and rebuild the index first.")

    se = sub.add_parser("search", help="Hybrid search with per-list contributions.")
    se.add_argument("query")
    se.add_argument("--mode", choices=["hybrid", "semantic", "keyword"], default="hybrid")
    se.add_argument("--k", type=int, default=10)

    ask = sub.add_parser("ask", help="Search, then answer with [source p.N] citations.")
    ask.add_argument("question")
    ask.add_argument("--k", type=int, default=8)

    exp = sub.add_parser("experiment", help="Re-index a fork of main and compare retrieval.")
    exp.add_argument("--questions", type=Path, default=Path("eval/questions.jsonl"))
    exp.add_argument("--parsed-dir", type=Path, default=Path("corpus/parsed"))
    exp.add_argument("--pdf-dir", type=Path, default=Path("corpus/pdfs"))
    exp.add_argument("--keep", action="store_true", help="Keep the fork + its Meili index.")
    exp.add_argument("--project", default=None, help="Override KISENON_PROJECT_ID.")

    for sp in (ing, exp):
        sp.add_argument("--chunker", choices=list(CHUNKERS), default="block")
        sp.add_argument("--embedder", choices=EMBEDDERS, default="fastembed")
    for sp in (se, ask, exp):
        sp.add_argument("--no-rerank", action="store_true", help="Skip Voyage rerank-2.")
    return p


def fail(message: str, code: int = 2) -> int:
    sys.stderr.write(json.dumps({"error": message}) + "\n")
    return code


def need_key(embedder: str) -> None:
    key = KEY_FOR.get(embedder)
    if key and not os.environ.get(key):
        raise SetupError(f"{key} is not set (needed for the {embedder} embedder).")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise SetupError("DATABASE_URL is not set. See README 'Setup'.")
        meili_url = os.environ.get("MEILI_URL", "http://localhost:7700")
        meili = Meili(meili_url, os.environ.get("MEILI_MASTER_KEY", ""))
        if not meili.healthy():
            raise SetupError(
                f"Meilisearch is not reachable at {meili_url}. Run `docker compose up -d`."
            )
        if hasattr(args, "embedder"):
            need_key(args.embedder)
        reranker = None
        if not getattr(args, "no_rerank", True):
            if os.environ.get("VOYAGE_API_KEY"):
                reranker = voyage_reranker()
            else:
                event("no VOYAGE_API_KEY", action="skipping rerank")
        import psycopg

        with psycopg.connect(url, autocommit=True) as conn:
            handler = {"ingest": cmd_ingest, "search": cmd_search, "ask": cmd_ask,
                       "experiment": cmd_experiment}[args.command]
            return handler(args, conn, meili, reranker)
    except (SetupError, IndexMismatch, keon.KeonError) as e:
        return fail(str(e))


def cmd_ingest(args, conn, meili, _reranker) -> int:
    summary = ingest(conn, meili, index_name("main"), parsed_dir=args.parsed_dir,
                     pdf_dir=args.pdf_dir, chunker=args.chunker,
                     embedder=get_embedder(args.embedder), reset=args.reset)
    print(f"Ingested {summary['chunks']} chunks from {summary['documents']} documents "
          f"into {summary['index']} + rag_complex.chunks.")
    print(json.dumps(summary))
    return 0 if summary["documents"] else 1


def embedder_for(conn):
    meta = read_meta(conn)
    if not meta:
        raise SetupError("No index found. Run `uv run rag-complex ingest` first.")
    need_key(meta["embedder"])
    return get_embedder(meta["embedder"])


def _public(h: dict) -> dict:
    keys = ("id", "source", "page_start", "page_end", "heading_context", "score", "contributions")
    return {k: h[k] for k in keys}


def _print_hits(hits: list[dict]) -> None:
    for i, h in enumerate(hits, 1):
        c = h["contributions"]
        print(f"{i:>2}. [{h['source']} p.{h['page_start']}] {h['heading_context'][:70]}\n"
              f"    rrf={h['score']} vector={c['vector']} keyword={c['keyword']} "
              f"rerank={c['rerank']}\n    {h['text'][:160].replace(chr(10), ' ')}")


def cmd_search(args, conn, meili, reranker) -> int:
    hits = search(args.query, conn=conn, meili=meili, index=index_name("main"),
                  embedder=embedder_for(conn), mode=args.mode, k=args.k, reranker=reranker)
    _print_hits(hits)
    print(json.dumps({"query": args.query, "mode": args.mode, "hits": [_public(h) for h in hits]}))
    return 0 if hits else 1


def cmd_ask(args, conn, meili, reranker) -> int:
    hits = search(args.question, conn=conn, meili=meili, index=index_name("main"),
                  embedder=embedder_for(conn), k=args.k, reranker=reranker)
    text = None
    if hits and os.environ.get("ANTHROPIC_API_KEY"):
        text = answer(args.question, hits)
        print(f"Answer: {text}\n")
    elif hits:
        event("no ANTHROPIC_API_KEY", action="printing hits instead of an answer")
    _print_hits(hits)
    print(json.dumps({"question": args.question, "answer": text, "model": MODEL if text else None,
                      "hits": [_public(h) for h in hits]}))
    return 0 if hits else 1


def answer(question: str, hits: list[dict], client=None) -> str:
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    context = "\n\n".join(f"[{h['source']} p.{h['page_start']}] ({h['heading_context']})\n"
                          f"{h['text']}" for h in hits)
    resp = client.messages.create(
        model=MODEL, max_tokens=4096, output_config={"effort": "low"},
        system=("Answer only from the excerpts. Cite each claim with the excerpt's label "
                "exactly as written, e.g. [2210.17323 p.5]. Tables are HTML. If the excerpts "
                "don't answer the question, say so."),
        messages=[{"role": "user", "content": f"Excerpts:\n\n{context}\n\nQuestion: {question}"}],
    )
    if resp.stop_reason == "refusal":
        return "(the model declined to answer this question)"
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def cmd_experiment(args, conn, meili, reranker) -> int:
    project = args.project or os.environ.get("KISENON_PROJECT_ID")
    if not project:
        raise SetupError("KISENON_PROJECT_ID is not set (and --project not given).")
    questions = load_questions(args.questions)
    main_emb = embedder_for(conn)
    fork_emb = main_emb if args.embedder == main_emb.name else get_embedder(args.embedder)
    main_meta = read_meta(conn)
    name = f"rag-exp-{secrets.token_hex(3)}"
    fork_index = index_name(name)
    branch_id = None
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # run the finally on kill
    import psycopg

    try:
        t0 = time.monotonic()
        branch_id = keon.create_branch(project=project, name=name)
        event("fork created", branch=name, id=branch_id,
              duration_ms=int((time.monotonic() - t0) * 1000))
        with psycopg.connect(keon.get_branch_url(project=project, branch=name),
                             autocommit=True) as fork:
            summary = ingest(fork, meili, fork_index, parsed_dir=args.parsed_dir,
                             pdf_dir=args.pdf_dir, chunker=args.chunker, embedder=fork_emb,
                             reset=True)
            event("fork indexed", chunks=summary["chunks"], duration_ms=summary["duration_ms"])
            res_main = run_eval(questions, lambda q: search(
                q, conn=conn, meili=meili, index=index_name("main"), embedder=main_emb,
                k=10, reranker=reranker))
            res_fork = run_eval(questions, lambda q: search(
                q, conn=fork, meili=meili, index=fork_index, embedder=fork_emb,
                k=10, reranker=reranker))
        print(f"main: chunker={main_meta.get('chunker')} embedder={main_meta.get('embedder')}   "
              f"fork: chunker={args.chunker} embedder={args.embedder}   "
              f"questions={len(questions)} rerank={'on' if reranker else 'off'}\n")
        print(format_table(res_main, res_fork))
        print(json.dumps({
            "branch": {"name": name, "id": branch_id, "kept": args.keep},
            "questions": len(questions),
            "main": {**res_main, "chunker": main_meta.get("chunker"),
                     "embedder": main_meta.get("embedder")},
            "fork": {**res_fork, "chunker": args.chunker, "embedder": args.embedder},
        }))
        return 0
    finally:
        if args.keep:
            event("kept", branch=name, meili_index=fork_index)
        else:
            _cleanup(meili, fork_index, branch_id)


def _cleanup(meili, fork_index: str, branch_id: str | None) -> None:
    try:
        meili.delete_index(fork_index)
        event("meili index deleted", index=fork_index)
    except Exception as e:  # noqa: BLE001
        event("cleanup failed", index=fork_index, error=e)
    if branch_id:
        try:
            keon.delete_branch(branch_id=branch_id)
            event("fork deleted", id=branch_id)
        except Exception as e:  # noqa: BLE001
            event("cleanup failed", run=f"keon branches delete --cascade {branch_id}", error=e)


if __name__ == "__main__":
    raise SystemExit(main())
