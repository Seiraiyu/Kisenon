"""fulltext-search CLI: Postgres full-text search with a pg_trgm fuzzy fallback."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]  # examples/fulltext-search

FTS_SQL = """
SELECT id, title, ts_rank_cd(tsv, q) AS rank,
       ts_headline('english', body, q,
                   'StartSel=[, StopSel=], MaxFragments=2, MaxWords=18, MinWords=6') AS snippet
FROM fulltext_search.articles, websearch_to_tsquery('english', %(q)s) AS q
WHERE tsv @@ q
ORDER BY rank DESC
LIMIT %(k)s
"""

# `q <% title`: word_similarity(q, title) above pg_trgm.word_similarity_threshold;
# served by the gin_trgm_ops index on title.
FUZZY_SQL = """
SELECT id, title, word_similarity(%(q)s, title) AS rank, left(body, 100) || '...' AS snippet
FROM fulltext_search.articles
WHERE %(q)s <%% title
ORDER BY rank DESC
LIMIT %(k)s
"""


def load(conn: Any) -> int:
    conn.execute((ROOT / "schema.sql").read_text())
    lines = (ROOT / "data" / "articles.jsonl").read_text().splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO fulltext_search.articles (title, body) VALUES (%s, %s)",
            [(r["title"], r["body"]) for r in rows],
        )
    return len(rows)


def search(conn: Any, q: str, k: int = 5) -> tuple[str, list[dict]]:
    mode = "fts"
    rows = conn.execute(FTS_SQL, {"q": q, "k": k}).fetchall()
    if not rows:
        mode = "fuzzy"
        conn.execute("SET pg_trgm.word_similarity_threshold = 0.3")
        rows = conn.execute(FUZZY_SQL, {"q": q, "k": k}).fetchall()
    hits = [
        {"id": r[0], "title": r[1], "rank": round(float(r[2]), 4), "snippet": r[3]} for r in rows
    ]
    return mode, hits


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(prog="fulltext-search", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("load", help="(Re)create schema fulltext_search and load data/articles.jsonl.")
    s = sub.add_parser("search", help="Search (web-style syntax: quotes, OR, -exclude).")
    s.add_argument("query")
    s.add_argument("--k", type=int, default=5)
    args = p.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        print(json.dumps({"error": "DATABASE_URL is not set.", "hint": "README#setup"}),
              file=sys.stderr)
        return 2
    with psycopg.connect(url, autocommit=True) as conn:
        if args.command == "load":
            n = load(conn)
            print(f"Loaded {n} articles into fulltext_search.articles")
            print(json.dumps({"loaded": n}))
            return 0
        mode, hits = search(conn, args.query, args.k)
    print(f"[mode: {mode} | hits={len(hits)}]", file=sys.stderr)
    for h in hits:
        print(f"{h['rank']:.4f}  [{h['id']}] {h['title']}\n        {h['snippet']}")
    print(json.dumps({"query": args.query, "mode": mode, "hits": hits}))
    return 0 if hits else 1


if __name__ == "__main__":
    raise SystemExit(main())
