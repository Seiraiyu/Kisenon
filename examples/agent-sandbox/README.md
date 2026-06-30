# agent-sandbox

Give an LLM a *fork* of your Postgres database — not your production database —
and let it run any SQL it wants to answer a question.

The agent can `DELETE`, `DROP`, `ALTER`, `CREATE INDEX` — anything. When it
answers (or hits a budget cap), the fork is destroyed. Your production data is
never touched.

This is the **read/explore** half of the AI-agent loop that pairs with
[`examples/branch-test`](../branch-test/)'s **write/migrate** half.

## Why this needs Kisenon

A read-only text-to-SQL agent against your prod database is the current state
of the art. It can answer "how many users signed up last month?" but it can't
honestly answer questions that *need mutation* to verify:

- "How many rows would this `DELETE` actually remove?"
- "Would `CREATE INDEX ON orders(customer_id, created_at DESC)` help?"
- "Are any `VARCHAR(50)` columns close to their length limit?"

To do those without Kisenon you'd need a staging copy that drifts, a snapshot
before every agent run, or to wrap every query in `BEGIN…ROLLBACK` and pray.
With Kisenon: `keon branches create` (~500 ms) → agent has its own real-data
sandbox → branch deleted on exit. No drift, no idle cost.

## What you need

- A Kisenon account with an alpha invite. Email **alpha@kisenon.com** with
  subject `Alpha access` if you don't have one.
- `keon` CLI installed and logged in (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- Postgres client tools (`psql`).
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- An LLM API key — `ANTHROPIC_API_KEY` (default) or `OPENAI_API_KEY`.

## Setup

```bash
cd examples/agent-sandbox
uv sync

cp .env.example .env
# edit .env:
#   KISENON_PROJECT_ID=<your project id>
#   ANTHROPIC_API_KEY=<key>
#   KISENON_URL=<connection string for your main branch>
```

To get your project id and main URL:

```bash
keon projects list -o json | jq '.projects[] | {id, name}'
keon connection-string main --project <project-id> -o json | jq -r '.connection_string'
```

Apply the demo dataset once to `main`:

```bash
psql "$KISENON_URL" -f setup.sql
```

That seeds 10,000 users, 1,000 products, 50,000 orders, ~200,000 order_items
on `main`. Each fork is a copy-on-write clone of this state.

## Three questions a normal text-to-SQL agent can't answer

### Demo 1 — "How many users would this DELETE actually remove?"

```bash
uv run agent-sandbox ask --question \
  "How many users would 'DELETE FROM users WHERE last_login < NOW() - INTERVAL ''2 years''' actually remove? Run it on the fork and tell me."
```

The agent introspects the schema, runs the DELETE on the fork, and reports
the actual rowcount. Expected: ~5,000 (50% of 10,000 with a uniform-random
`last_login` over 4 years). The fork is destroyed after; main is unchanged.

### Demo 2 — "Would this index help the slow homepage query?"

```bash
uv run agent-sandbox ask --question \
  "Our homepage runs 'SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 10'. Would 'CREATE INDEX ON orders(customer_id, created_at DESC)' speed it up? Use EXPLAIN ANALYZE to verify before and after on the fork."
```

The agent EXPLAINs the seq-scan baseline, creates the index on the fork,
EXPLAINs again, and reports the speedup with real numbers.

### Demo 3 — "Are any VARCHAR columns close to their length limit?"

```bash
uv run agent-sandbox ask --question \
  "Which VARCHAR columns in our schema are within 10% of their declared length limit? Treat that as 'at risk of silent truncation' and report the worst offenders."
```

The agent queries `information_schema.columns` for character_maximum_length,
joins against per-column `SELECT max(length(...))` queries it constructs on
the fork, and ranks the at-risk columns. Realistic schema audit; safe to run
because the fork dies after.

## Output shape

The CLI streams progress events to **stderr**, then prints the human answer
+ a single JSON line to **stdout**:

```bash
$ uv run agent-sandbox ask --question "..."

# stderr (you watch this go by):
[ask start: how many users…? | provider=anthropic | model=claude-sonnet-4-6]
[branch forked: 547ms]
[run_sql: SELECT count(*) FROM users WHERE last_login < NOW() - INTERVAL '2 years']
[run_sql done: 4998 | duration_ms=9]
[run_sql: DELETE FROM users WHERE last_login < NOW() - INTERVAL '2 years']
[run_sql done: 4998 | duration_ms=142]
[branch deleted: br_id]

# stdout (you pipe this to jq or another agent):
Answer: 4,998 users would be removed (verified by running the DELETE on a fork).
{"answer":"4,998 users…","branch":{…},"queries":[…],"cap_hit":null,"provider":"anthropic","model":"claude-sonnet-4-6","total_duration_ms":2102}
```

## Flags

| Flag | Meaning |
|---|---|
| `--question STR` (required) | The question the agent should answer. |
| `--provider {anthropic,openai}` | LLM provider. Default `anthropic`. |
| `--model ID` | Override the provider's default model. |
| `--max-queries N` | Max `run_sql` calls before forced summary. Default 10. |
| `--max-wall-s N` | Total wall-clock budget. Default 120. |
| `--row-cap N` | Rows kept per SQL result in the JSON record. Default 1000. |
| `--pretty` | Suppress the JSON line; only print the human answer. |
| `--always-delete` | Delete the branch even on cap-hit / fatal. |
| `--project ID` | Override `KISENON_PROJECT_ID`. |
| `--name NAME` | Override the auto-generated branch name. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Agent answered within caps. |
| `1` | A budget cap fired; best-effort answer still returned. |
| `2` | Fatal error before the agent loop (missing env, keon not on PATH, branch creation failed, provider auth failure). |

## Limitations (v1)

- One-shot only. Interactive REPL is a planned v2.
- Anthropic + OpenAI only. Cohere/Gemini deliberately out of scope.
- No streaming of the model's reasoning text — only structured events.
- The agent has to introspect the schema itself (one or two extra queries) —
  there's no pre-loaded schema description.

## Troubleshooting

### `KISENON_PROJECT_ID is not set`
Source `.env` (or pass `--project <id>`).

### `ANTHROPIC_API_KEY is not set`
Add to `.env`. If you're using `--provider openai`, set `OPENAI_API_KEY` instead.

### `psql: error: connection to server … FATAL: endpoint not found`
Your `KISENON_URL` references an endpoint that's been suspended. Fetch a fresh URL:
`keon connection-string main --project "$KISENON_PROJECT_ID" -o json`.

### `keon branches delete <id>` returns `cp 409`
That branch still has an attached compute endpoint. agent-sandbox always passes
`--cascade` to delete, so this shouldn't happen during normal use; if you see it
running cleanup manually, use `keon branches delete --cascade <id>`.

### Agent gives up with `cap_hit: max_queries`
Your question may need more exploration than the default 10 queries. Re-run with
`--max-queries 20`. The previous run's branch is preserved (see the JSON's
`branch.url`) so you can inspect what the agent did.
