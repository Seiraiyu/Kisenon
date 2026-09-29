# index-advisor

Your slowest queries, from `pg_stat_statements` → an LLM proposes indexes →
**every candidate is built and benchmarked on its own Kisenon fork** →
ranked recommendations with ready-to-run `CREATE INDEX CONCURRENTLY` SQL.
Nothing is written to `main`.

## Why this needs Kisenon

An index suggestion is a guess until you build it on real data and look at
the plan. Building five candidates on production takes locks, disk and
nerve; building them on staging measures the wrong data. Each candidate
here gets its own copy-on-write fork of `main` (about 2 s each, including
waiting for the fork's compute to be ready), is built without
`CONCURRENTLY` (nobody else is on the fork), measured, and the fork is
deleted.

This is the batch version of
[agent-sandbox](../agent-sandbox/) demo 2 ("would this index help?"): instead
of asking about one query you name, it takes the top statements by total
time and tests several candidates, one fork each.

## What you need

- A Kisenon account, `keon` CLI installed and logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- `psql`, Python 3.11+, [uv](https://docs.astral.sh/uv/).
- The `pg_stat_statements` extension on `main` (Setup step 3 creates it).
- An LLM key (see below).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `KISENON_PROJECT_ID` | `keon projects list -o json` | required for `advise` | exit 2 |
| `KISENON_URL` | `keon connection-string main --project <id>` | required (read-only use) | exit 2 |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | required for `advise --provider anthropic` (default) | exit 2 `ANTHROPIC_API_KEY is not set.`, no fork created; `check` and `workload` still work |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/) | only for `--provider openai` | same, for that provider |

## Setup

```bash
cd examples/index-advisor
uv sync
cp .env.example .env        # fill in KISENON_PROJECT_ID, KISENON_URL, ANTHROPIC_API_KEY
set -a; . ./.env; set +a
psql "$KISENON_URL" -f setup.sql                                               # 1. data
psql "$KISENON_URL" -c 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements'     # 2. stats
uv run index-advisor check                                                     # 3. verify
```

`check` prints `pg_stat_statements: ok (…)` and exits 0, or exits 2 with
what to do (see Troubleshooting).

## Demo

```bash
uv run index-advisor workload --rounds 50
uv run index-advisor advise --match '%index_advisor.%'
```

`workload` runs 150 parameterized reads on `main` (orders by customer,
counts by status + date, customers by `lower(email)`) so the statistics
have something to rank. `--match` keeps other schemas' statements out.

Real output from a run on a Kisenon project (stderr events first, then the
ranked list on stdout; the JSON line is abbreviated here). The whole run,
four forks included, took 40 s:

```text
$ uv run index-advisor check
pg_stat_statements: ok (16 SELECT statements recorded in this database)
{"pg_stat_statements": "ok", "statements": 16}

$ uv run index-advisor workload --rounds 50
Ran 150 statements on main. Next: uv run index-advisor advise
{"statements": 150}

$ uv run index-advisor advise --match '%index_advisor.%'
[advise start: 4 | model=claude-sonnet-5]
[branch forked: 78225146-8279-4ab1-8e98-bf8aac13b145 | index=CREATE INDEX orders_status_created_at_idx ON index_advisor.orders USING btree (s | duration_ms=2397]
[measured: CREATE INDEX orders_status_created_at_idx ON index_advisor.orders USING btree (s | before_ms=78.66 | after_ms=30.5 | used=True]
[branch forked: 03efa868-1551-4566-8b7a-e94183b1711c | index=CREATE INDEX orders_customer_id_created_at_idx ON index_advisor.orders USING btr | duration_ms=2420]
[measured: CREATE INDEX orders_customer_id_created_at_idx ON index_advisor.orders USING btr | before_ms=45.45 | after_ms=0.08 | used=True]
[branch forked: d4233f4d-88da-4e40-80fd-f85af1a6d284 | index=CREATE INDEX orders_customer_id_created_at_idx ON index_advisor.orders USING btr | duration_ms=2371]
[measured: CREATE INDEX orders_customer_id_created_at_idx ON index_advisor.orders USING btr | before_ms=42.92 | after_ms=0.02 | used=True]
[branch forked: a4f02d6f-70a2-438e-8a0a-ed953ae6fd72 | index=CREATE INDEX customers_lower_email_idx ON index_advisor.customers USING btree (l | duration_ms=1794]
[measured: CREATE INDEX customers_lower_email_idx ON index_advisor.customers USING btree (l | before_ms=9.35 | after_ms=0.04 | used=True]
1. recommended: 78.66 ms -> 30.50 ms per call, 50 calls, ~2408 ms saved; size 32.3 MB
   CREATE INDEX CONCURRENTLY orders_status_created_at_idx ON index_advisor.orders USING btree (status, created_at);
   why: Composite index on status and created_at enables efficient filtering and range scan for the count query.
   write overhead: 1000000 writes since stats reset; each would maintain 2 indexes (was 1)
2. recommended: 45.45 ms -> 0.08 ms per call, 29 calls, ~1316 ms saved; size 30.1 MB
   CREATE INDEX CONCURRENTLY orders_customer_id_created_at_idx ON index_advisor.orders USING btree (customer_id, created_at DESC);
   why: Composite index matching filter column and sort order avoids sorting and speeds up top-N retrieval per customer.
   write overhead: 1000000 writes since stats reset; each would maintain 2 indexes (was 1)
3. recommended: 42.92 ms -> 0.02 ms per call, 21 calls, ~901 ms saved; size 30.1 MB
   CREATE INDEX CONCURRENTLY orders_customer_id_created_at_idx ON index_advisor.orders USING btree (customer_id, created_at DESC);
   why: Same composite index serves this identical query pattern with different literal values.
   write overhead: 1000000 writes since stats reset; each would maintain 2 indexes (was 1)
4. recommended: 9.35 ms -> 0.04 ms per call, 50 calls, ~466 ms saved; size 4.8 MB
   CREATE INDEX CONCURRENTLY customers_lower_email_idx ON index_advisor.customers USING btree (lower(email));
   why: Expression index on lower(email) allows fast equality lookups matching the case-insensitive filter.
   write overhead: 100000 writes since stats reset; each would maintain 2 indexes (was 1)
{"model": "claude-sonnet-5", "provider": "anthropic", "recommendations": [{"index_sql": "CREATE INDEX CONCURRENTLY orders_status_created_at_idx ON index_advisor.orders USING btree (status, created_at);", "table": "index_advisor.orders", "queryid": "1169289851461510755", "sample_query": "SELECT count(*) FROM index_advisor.orders WHERE status = 'shipped' AND created_at >= '2024-01-01'", ..., "branch": "index-advisor-bace4e08-1", "error": null}, ...]}
```

Recommendations 2 and 3 are the same index. The orders-by-customer query
shows up under two `queryid`s (29 + 21 calls), which is why the model
proposed it twice; see Limitations. Afterwards no `index-advisor-*` branches
remained, and `main` still had only its two primary-key indexes.

## How candidates are ranked

`est_saved_ms = (before_ms − after_ms) × calls`, where `calls` comes from
`pg_stat_statements` for the statement the candidate targets. A candidate
whose index doesn't appear in the post-build plan scores 0 no matter what
the timings say. `before/after_ms` are medians of 3 `EXPLAIN ANALYZE` runs
of the model's `sample_query` (the statement with literal values filled in),
after one warm-up.

## Flags (`advise`)

| Flag | Meaning |
|---|---|
| `--match PATTERN` | `ILIKE` filter on statement text. Default `%` (everything). |
| `--top N` | Statements sent to the model. Default 5. |
| `--max-candidates N` | Candidates benchmarked (one fork each). Default 5. |
| `--provider`, `--model` | Default `anthropic` / `claude-sonnet-5`. |
| `--project ID` | Override `KISENON_PROJECT_ID`. |
| `--keep` | Keep every candidate fork for inspection. |
| `--pretty` | No JSON line. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | At least one candidate measurably helped. |
| `1` | Candidates ran but none helped (or the model proposed nothing usable). |
| `2` | `pg_stat_statements` missing/unreadable, no statements recorded, missing env/key, or LLM failure. |

## Troubleshooting

### `pg_stat_statements is not installed in this database`
Run `psql "$KISENON_URL" -c 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements'`.
If Postgres answers that the extension isn't available, your plan/region
doesn't ship it — this example can't run there.

### `pg_stat_statements is installed but can't be read`
The library must be preloaded by the server (`shared_preload_libraries`).
That's a platform setting, not something you can change from SQL; contact
Kisenon support.

### `no SELECT statements matching …`
Statistics live in the compute's memory and reset when `main`'s compute
restarts (for example after scaling to zero). Re-run `workload`, then
`advise` right after.

## Limitations

- Reads only (`SELECT`/`WITH`); write statements aren't sent to the model.
- Write overhead is an estimate from `pg_stat_user_tables` counters, not a
  measured insert benchmark.
- Candidates run sequentially; five candidates on a large table take a while.
- Candidates aren't de-duplicated. `pg_stat_statements` can record one query
  shape under several `queryid`s, for example when the driver sends a small
  integer as `int2` in one call and as `int4` in another (psycopg picks the
  type from the value). The model may then propose the same index twice, and
  each copy is benchmarked on its own fork.
- `--provider openai` is untested unless noted in the PR.
