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
of `main` in ~500 ms, works in isolation, and the comparison is fair. Main
is never touched.

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
[branch forked: … | strategy=index | ms=…]
[branch forked: … | strategy=rewrite | ms=…]
[branch forked: … | strategy=matview | ms=…]
[apply: index | sql=CREATE INDEX … ON events (account_id, created_at)]
[measured: index | before_ms=… | after_ms=… | correct=True]
...
[branch deleted: …]  ×3
strategy   correct   before_ms   after_ms  note
index      yes           …          …      …
rewrite    yes           …          …      …
matview    yes           …          …      …
Winner: … — … ms (goal 5 ms: met)
{"goal_ms": 5.0, "winner": "…", "met_goal": true, …}
```

(Numbers are filled in from the live verification run.)

The `rewrite` agent usually can't win: without an index, any query over
`events` still reads the table. That's the point of measuring instead of
trusting the proposal.

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
- `--provider openai` is untested unless noted in the PR.
