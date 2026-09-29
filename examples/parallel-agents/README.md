# parallel-agents

Give one slow query to three LLM agents at once — one adds an index, one
rewrites the SQL, one builds a materialized view — each on **its own
Kisenon fork**. The harness measures every proposal with `EXPLAIN ANALYZE`,
checks it returns the same rows, and picks the winner by the numbers.
Losing forks are destroyed.

## Why this needs Kisenon

Three agents trying three fixes against one database step on each other: an
index created by agent A makes agent B's rewrite look fast. You'd need three
full copies of the data. With Kisenon each agent gets a copy-on-write fork
of `main` (1.4–3.2 s each, created concurrently, in our runs), works in
isolation, and the comparison is fair. Main is never touched.

## What you need

- A Kisenon account, `keon` CLI installed and logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- `psql`, Python 3.11+, [uv](https://docs.astral.sh/uv/).
- An LLM key (see below).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `KISENON_PROJECT_ID` | `keon projects list -o json` | required | exit 2 |
| `KISENON_URL` | `keon connection-string main --project <id>` | setup only | you can't apply `setup.sql` |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | required for `--provider anthropic` (default) | exit 2 `ANTHROPIC_API_KEY is not set.`, no fork created |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/) | only for `--provider openai` | same, for that provider |

## Setup

```bash
cd examples/parallel-agents
uv sync
cp .env.example .env        # fill in KISENON_PROJECT_ID, KISENON_URL, ANTHROPIC_API_KEY
set -a; . ./.env; set +a
psql "$KISENON_URL" -f setup.sql
```

`setup.sql` creates schema `parallel_agents` with 1,000,000 `events` rows and
no secondary indexes. `dashboard.sql` is the slow query (per-day counts for
one account over June).

## Demo

```bash
uv run parallel-agents --goal-ms 5
```

```text
[race start: 3 | goal_ms=5.0 | model=claude-sonnet-5]
[branch forked: 0cfbd0e2-68dc-4ccd-80f5-07eeb20e6c81 | strategy=rewrite | ms=1756]
[branch forked: 1d669145-484c-4e91-b6d3-149292d7157d | strategy=index | ms=1793]
[branch forked: 809504bf-f598-4906-8543-9618647f6641 | strategy=matview | ms=1818]
[apply: index | sql=CREATE INDEX events_account_created_kind_idx ON events (account_id, created_at, kind)]
[agent failed: rewrite | error=ValueError: rewrite strategy proposed DDL; only the query may change]
[measured: index | before_ms=49.58 | after_ms=0.06 | correct=True]
[apply: matview | sql=CREATE MATERIALIZED VIEW events_daily_kind_mv AS SELECT account_id, date_trunc('day', created_at) AS day, kind, count(*)]
[apply: matview | sql=CREATE UNIQUE INDEX events_daily_kind_mv_idx ON events_daily_kind_mv (account_id, day, kind)]
[measured: matview | before_ms=49.52 | after_ms=0.11 | correct=True]
[branch deleted: 0cfbd0e2-68dc-4ccd-80f5-07eeb20e6c81]
[branch deleted: 1d669145-484c-4e91-b6d3-149292d7157d]
[branch deleted: 809504bf-f598-4906-8543-9618647f6641]
strategy   correct   before_ms   after_ms  note
index      yes           49.58       0.06  A composite index on (account_id, created_at, kind) lets PostgreSQL use an index scan to quickly filter and access only the matching rows, avoiding the costly sequential scan and sort.
rewrite    no            46.42          -  ValueError: rewrite strategy proposed DDL; only the query may change
matview    yes           49.52       0.11  Precomputing per-account/day/kind counts in a materialized view with a covering unique index lets the filtered, ordered query be answered via a fast index scan instead of a full table scan and aggregation.
Winner: index — 0.06 ms (goal 5 ms: met)
  CREATE INDEX events_account_created_kind_idx ON events (account_id, created_at, kind)
  -- query: SELECT date_trunc('day', created_at) AS day, kind, count(*) AS n FROM events WHERE account_id = 42 AND created_at >= TIMESTAMPTZ '2026-06-01 00:00:00+00' GROUP BY 1, 2 ORDER BY 1, 2
{"goal_ms": 5.0, "winner": "index", "met_goal": true, "kept_branch": null, "provider": "anthropic", "model": "claude-sonnet-5", "candidates": [...]}
```

(Real output from the live verification run; the JSON line's `candidates`
array is elided. It has each agent's SQL, timings and error.)

The `rewrite` agent usually can't win: without an index, any query over
`events` still reads the table. Models know this and often propose an index
anyway. The harness rejects any `setup_sql` from `rewrite` (as in the run
above), so each strategy is judged on what it's allowed to do. That's the
point of measuring instead of trusting the proposal.

## Reading the result

- **correct** — the new query returned exactly the same rows (as a multiset)
  as the original on that fork. Incorrect candidates can't win.
- **before/after_ms** — median of 5 `EXPLAIN (ANALYZE)` runs after one warm-up.
- A materialized view is fast because it's precomputed; it goes stale until
  `REFRESH MATERIALIZED VIEW`. Decide whether that's acceptable before you
  ship it. The winner's SQL is printed; nothing is applied to `main`.

## Flags

| Flag | Meaning |
|---|---|
| `--query-file PATH` | The slow query. Default `dashboard.sql`. |
| `--goal-ms N` | Target. Default 5. |
| `--strategies LIST` | Comma list of `index,rewrite,matview`; one agent (and fork) each. |
| `--provider`, `--model` | Default `anthropic` / `claude-sonnet-5`. |
| `--project ID` | Override `KISENON_PROJECT_ID`. |
| `--keep` | Keep the winner's fork (its name is in the JSON). Losers are always deleted. |
| `--pretty` | No JSON line. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | A correct candidate met the goal. |
| `1` | No correct candidate met the goal (the report still shows what happened). |
| `2` | Setup failure: missing env/key, bad flags, no fork could be created. |

## Limitations

- One LLM call per agent, no iteration. Agents don't see each other's results.
- Queries run in the `parallel_agents` schema (`SCHEMA` in `measure.py`).
- Timings on a fresh fork include cold-cache effects; the warm-up run and the
  median reduce but don't remove noise.
- If you press Ctrl-C mid-race the harness waits for running agents to finish
  their current step, then deletes every fork it created.
- `--provider openai` is untested (no OpenAI key during verification).
