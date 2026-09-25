"""rag-simple CLI: `ingest <dir>` and `ask "<question>"`.

stderr: `[event: ...]` progress lines. stdout: the human answer, then one JSON line.
Exit codes: 0 ok, 1 nothing to do / no hits, 2 fatal setup error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from rag_simple.chunker import chunk_text
from rag_simple.embed import EMBEDDERS, KEY_FOR, get_embedder
from rag_simple.store import DimensionMismatch, ensure_schema, replace_source, search


def event(label: str, **fields) -> None:
    body = " | ".join(f"{k}={v}" for k, v in fields.items())
    sys.stderr.write(f"[{label}{': ' + body if body else ''}]\n")


def fail(message: str, code: int = 2) -> int:
    sys.stderr.write(json.dumps({"error": message}) + "\n")
    return code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rag-simple", description="Minimal RAG on Kisenon.")
    sub = p.add_subparsers(dest="command", required=True)
    ing = sub.add_parser("ingest", help="Chunk + embed every .md/.txt file under DIR.")
    ing.add_argument("dir", type=Path)
    ing.add_argument("--reset", action="store_true", help="Drop and rebuild the tables first.")
    ask = sub.add_parser("ask", help="Retrieve top-k chunks and answer with citations.")
    ask.add_argument("question")
    ask.add_argument("--k", type=int, default=5)
    for sp in (ing, ask):
        sp.add_argument("--embedder", choices=EMBEDDERS, default="fastembed")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    if not url:
        return fail("DATABASE_URL is not set. See README 'Setup'.")
    if args.embedder in KEY_FOR and not os.environ.get(KEY_FOR[args.embedder]):
        return fail(f"{KEY_FOR[args.embedder]} is not set (needed for --embedder {args.embedder}).")

    import psycopg

    embedder = get_embedder(args.embedder)
    with psycopg.connect(url, autocommit=True) as conn:
        try:
            ensure_schema(conn, embedder.dim, reset=getattr(args, "reset", False))
        except DimensionMismatch as e:
            return fail(str(e))
        if args.command == "ingest":
            return _ingest(conn, args.dir, embedder)
        return _ask(conn, args.question, args.k, embedder)


def _ingest(conn, root: Path, embedder) -> int:
    started = time.monotonic()
    files = sorted(p for p in root.rglob("*") if p.suffix in (".md", ".txt"))
    total = 0
    for path in files:
        chunks = chunk_text(path.read_text(encoding="utf-8"))
        replace_source(conn, str(path), chunks, embedder.embed_documents(chunks))
        event("ingested", file=path, chunks=len(chunks))
        total += len(chunks)
    summary = {
        "files": len(files), "chunks": total, "embedder": embedder.name, "dim": embedder.dim,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    print(f"Ingested {total} chunks from {len(files)} files.")
    print(json.dumps(summary))
    return 0 if files else 1


def _ask(conn, question: str, k: int, embedder) -> int:
    from rag_simple.answer import MODEL, answer, format_sources

    hits = search(conn, embedder.embed_query(question), k)
    event("retrieved", hits=len(hits), top_score=hits[0]["score"] if hits else None)
    text = None
    if not hits:
        print("No chunks found. Run `rag-simple ingest corpus` first.")
    elif os.environ.get("ANTHROPIC_API_KEY"):
        text = answer(question, hits)
        print(f"Answer: {text}\n\nSources:\n{format_sources(hits)}")
    else:
        event("no ANTHROPIC_API_KEY", action="printing retrieved chunks instead of an answer")
        for i, h in enumerate(hits, 1):
            print(f"[{i}] {h['source']} (chunk {h['ord']}, score {h['score']})\n{h['text']}\n")
    print(json.dumps({
        "question": question, "answer": text, "model": MODEL if text else None,
        "embedder": embedder.name,
        "hits": [{k_: h[k_] for k_ in ("source", "ord", "score")} for h in hits],
    }))
    return 0 if hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
