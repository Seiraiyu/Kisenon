# index-advisor

Your slowest queries, from `pg_stat_statements` → an LLM proposes indexes →
**every candidate is built and benchmarked on its own Kisenon fork** →
ranked recommendations with ready-to-run `CREATE INDEX CONCURRENTLY` SQL.
Nothing is written to `main`.

## Why this needs Kisenon

An index suggestion is a guess until you build it on real data and look at
the plan. Building five candidates on production takes locks, disk and
nerve; building them on staging measures the wrong data. Each candidate
here gets a ~500 ms copy-on-write fork of `main`, is built without
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

```text
[advise start: 3 | model=claude-sonnet-5]
[branch forked: … | index=CREATE INDEX ON index_advisor.orders (customer_id, created_at DESC) | duration_ms=…]
[measured: … | before_ms=… | after_ms=… | used=True]
[branch forked: …]
...
1. recommended: … ms -> … ms per call, 50 calls, ~… ms saved; size … MB
   CREATE INDEX CONCURRENTLY ON index_advisor.orders (customer_id, created_at DESC);
   why: …
   write overhead: … writes since stats reset; each would maintain 2 indexes (was 1)
2. …
{"model": "claude-sonnet-5", "provider": "anthropic", "recommendations": [...]}
```

(Numbers are filled in from the live verification run.)

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
- `--provider openai` is untested unless noted in the PR.
