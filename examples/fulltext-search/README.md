# fulltext-search

Search that lives inside Postgres: no extra service to run.

- `tsvector` **generated column** (title weighted above body) + **GIN** index
- `websearch_to_tsquery`, so users can type `"exact phrase"`, `OR`, `-exclude`
- `ts_rank_cd` ranking and `ts_headline` snippets (`[match]` highlighted)
- **`pg_trgm` fuzzy fallback** when full-text finds nothing (typos like `vacum`)

## What you need

- A Kisenon project (`keon login`), Python 3.11+, [uv](https://docs.astral.sh/uv/).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `DATABASE_URL` | `keon connection-string main --project <id>` | required | exits 2 |

No API keys needed.

## Setup

```bash
cd examples/fulltext-search
uv sync
cp .env.example .env   # set DATABASE_URL
uv run fulltext-search load
```
```
Loaded 20 articles into fulltext_search.articles
{"loaded": 20}
```

`load` drops and recreates schema `fulltext_search`, so it is safe to re-run.

## Demos

```bash
uv run fulltext-search search "connection pooling"
uv run fulltext-search search '"write-ahead log" -replication'
uv run fulltext-search search "vacum"
uv run fulltext-search search "brnaching"
```

Output from a run against Kisenon (stderr mode line, then ranked hits, then one JSON line,
shortened here to `[...]`):

```
[mode: fts | hits=1]
1.0952  [9] Connection pooling
        Postgres forks a process per [connection]
{"query": "connection pooling", "mode": "fts", "hits": [...]}

[mode: fts | hits=2]
1.4000  [7] The write-ahead log
        Every change is written to the [write]-[ahead] [log] before the data files. After a crash, Postgres replays
0.4000  [19] Point-in-time recovery
        With a base backup and archived [write]-[ahead] [log] you can restore a database to any moment
{"query": "\"write-ahead log\" -replication", "mode": "fts", "hits": [...]}

[mode: fuzzy | hits=1]
0.6667  [2] Vacuum and table bloat
        Updates and deletes leave dead tuples behind. Autovacuum reclaims the space and keeps the visibility...
{"query": "vacum", "mode": "fuzzy", "hits": [...]}

[mode: fuzzy | hits=2]
0.4286  [1] Database branching for AI agents
        A branch is a copy-on-write fork of a database. Agents can run destructive SQL on a branch and throw...
0.4000  [6] Fuzzy matching with trigrams
        The pg_trgm extension splits text into three-character sequences. Similarity and word_similarity fin...
{"query": "brnaching", "mode": "fuzzy", "hits": [...]}
```

`-replication` keeps "Streaming replication" out of the second result even though it
mentions the write-ahead log.

Exit codes: `0` hits, `1` no hits, `2` setup error.

## The SQL

See `schema.sql` and the two queries at the top of `src/fulltext_search/cli.py`. The whole
technique is:

```sql
SELECT id, title, ts_rank_cd(tsv, q) AS rank, ts_headline('english', body, q, '...') AS snippet
FROM fulltext_search.articles, websearch_to_tsquery('english', $1) AS q
WHERE tsv @@ q ORDER BY rank DESC LIMIT 5;
-- zero rows? then:
SET pg_trgm.word_similarity_threshold = 0.3;
SELECT id, title, word_similarity($1, title) AS rank FROM fulltext_search.articles
WHERE $1 <% title ORDER BY rank DESC LIMIT 5;
```

## Postgres FTS vs a search engine

[`rag-complex`](../rag-complex/) pairs pgvector with **Meilisearch** for keyword search.
Built-in FTS is the right default when you want one database, transactional consistency,
and joins with your own tables. Reach for a dedicated engine when you need typo tolerance on
every query (not just as a fallback), faceting at scale, or language-aware ranking beyond
`ts_rank_cd`.

## Limitations

- English stemming only (`'english'` config). Pick another text search config per language.
- The fuzzy fallback only matches titles; add a trigram index on `body` if you need more.
- With only 20 rows, `EXPLAIN` shows a `Seq Scan` (the planner rightly skips the GIN index on
  a table this small). The indexes pay off once the table grows.
