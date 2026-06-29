# agent-migrate

An LLM writes a schema migration, verifies it on a **scoped, disposable fork**
of your production database, and ships it to `main` only when *you* run an
explicit `promote`. The agent authors raw SQL, watches it pass (or fail) on the
fork, fixes its own mistakes on red, and never touches production directly.

This is the **write/migrate** half of the AI-agent loop. Where
[`examples/agent-sandbox`](../agent-sandbox/) hands the model a throwaway fork
to *explore*, agent-migrate hands it a fork to *change* — and adds a control
plane–enforced promote gate so a green migration still requires a deliberate
confirm before it lands on `main`.

## Why this needs Kisenon

Letting an LLM run migrations against production is obviously unsafe. The usual
workarounds all leak:

- A long-lived staging DB that drifts from prod, so "green on staging" lies.
- A `BEGIN…ROLLBACK` wrapper — which can't test anything that needs `COMMIT`
  (concurrent indexes, multi-transaction backfills) and still runs on prod.
- Handing the agent prod credentials and praying.

Kisenon's `keon sandbox` makes the safe path the easy path:

- **A scoped credential the agent can't escape.** `keon sandbox run` forks
  `main`, runs the migration against the *fork* under a role that can't reach
  `main`, and reports a green/red verdict. The agent only ever holds the
  fork's `$DATABASE_URL`.
- **An attributed action log.** Every statement the migration replayed is
  captured (`keon sandbox log <id>`), so a green sandbox carries a reviewable
  record of exactly what will be applied.
- **A promote/approve gate.** Going green does **not** touch `main`. The
  control plane replays the captured statements to `main` only on
  `keon sandbox promote`, and on a `human`-mode project that promote *parks*
  in `awaiting_approval` until an owner runs `keon sandbox approve`.

Compared to [`examples/branch-test`](../branch-test/), you no longer have to
hand-roll the fork, the scoped role, the verify harness, and the merge — the
sandbox primitive does all of it and attributes the result.

## What you need

- A Kisenon account with an alpha invite. Email **alpha@kisenon.com** with
  subject `Alpha access` if you don't have one.
- A **sandbox-enabled `keon` build**, logged in. Verify the command group
  exists:
  ```bash
  keon sandbox --help    # must list: run | promote | approve | discard | log | diff | create | list | get
  ```
  If `keon sandbox` is unknown, your binary predates the sandbox surface —
  upgrade keon (`curl -fsSL https://kisenon.com/install.sh | bash`).
- The demo region/project must have sandboxes **enabled**. If calls return
  `not_implemented` / `501`, ask your Kisenon operator to turn the feature on.
- Postgres client tools (`psql`).
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- An LLM API key — `ANTHROPIC_API_KEY` (default) or `OPENAI_API_KEY`.

## Setup

```bash
cd examples/agent-migrate
uv sync

cp .env.example .env
# edit .env:
#   KISENON_PROJECT_ID=<your project id>
#   KISENON_URL=<connection string for your main branch>   # read-only introspection only
#   ANTHROPIC_API_KEY=<key>
```

`KISENON_URL` is used **only** for read-only schema introspection (the agent's
`inspect_schema` tool). Every write happens on a scoped sandbox — never on the
URL in `.env`.

To get your project id and main URL:

```bash
keon projects list -o json | jq '.projects[] | {id, name}'
keon connection-string main --project <project-id> -o json | jq -r '.connection_string'
```

Apply the demo dataset once to each project's `main`:

```bash
psql "$KISENON_URL" -f setup.sql
```

That seeds 10,000 users, 1,000 products, 50,000 orders, ~200,000 order_items.
Note `orders` deliberately ships with **no `status` column and no index on
`customer_id`** — the demos add them. Each sandbox is a copy-on-write fork of
this state.

## Three demos

### Demo 1 — clean migration → promote (a `self`-promote project)

```bash
uv run agent-migrate ask --request \
  "Add a 'status' column to orders defaulting to 'pending', backfill existing rows, and index it for: SELECT * FROM orders WHERE customer_id=42 ORDER BY created_at DESC LIMIT 10"
```

The agent inspects the schema, authors the `ALTER`/backfill/`CREATE INDEX`,
and a `verify_sql` that RAISEs if any `status` is still null. `keon sandbox run`
applies both to a fork → **green**. Nothing has touched `main` yet. The output
prints a `promote_hint`; run it to land the change:

```bash
keon sandbox promote <green_sandbox_id>          # -> {"sandbox":{"status":"promoted"}}
psql "$KISENON_URL" -c '\d orders'               # main now has orders.status + the index
```

### Demo 2 — bad migration → red, no promote (proves the gate)

```bash
uv run agent-migrate ask --max-attempts 1 --request \
  "Add a NOT NULL 'tier' column to users with no default and no backfill"
```

The migration leaves existing rows with a null `tier` (or the `NOT NULL` add
fails outright); the verify RAISEs. `keon sandbox run` returns **red**,
`final_status` is `red`, the process exits `1`, and there is **no**
`promote_hint` to run — `main` is untouched. The failing sandbox is preserved
so you can inspect exactly what it tried:

```bash
keon sandbox log <red_sandbox_id>     # the captured statements + the failure
```

### Demo 3 — governed promote (a `human`-mode project)

Run the same request as Demo 1 against a project whose
`projects.promote_mode = 'human'`. The agent still gets a green sandbox, but
`promote` does not land the change — it **parks**:

```bash
keon sandbox promote <green_sandbox_id>   # -> {"sandbox":{"status":"awaiting_approval"}}
keon sandbox approve <green_sandbox_id>   # owner/admin only -> {"sandbox":{"status":"promoted"}}
```

This is the separation-of-duties path: the agent (or `--auto-promote`) can
*request* the promote, but a human owner makes the final commit.

## Output shape

The CLI streams progress events to **stderr**, then prints the human answer
plus a single JSON line to **stdout**:

```bash
$ uv run agent-migrate ask --request "Add a 'status' column to orders…"

# stderr (you watch this go by):
[ask start: Add a 'status' column to orders… | provider=anthropic | model=claude-sonnet-4-6]
[run_migration: attempt=1]
[verdict: green | sandbox=sb_abc123]

# stdout (you pipe this to jq or another agent):
Answer: The migration is green on sandbox sb_abc123. Promote with: keon sandbox promote sb_abc123
{"answer":"…","final_status":"green","green_sandbox_id":"sb_abc123","promote_hint":"keon sandbox promote sb_abc123","promoted":null,"promote_preview":[…],"attempts":[…],"provider":"anthropic","model":"claude-sonnet-4-6","total_duration_ms":8123}
```

## Flags

| Flag | Meaning |
|---|---|
| `--request STR` (required) | The plain-English schema change to make. |
| `--provider {anthropic,openai}` | LLM provider. Default `anthropic`. |
| `--model ID` | Override the provider's default model. |
| `--parent BRANCH` | Branch to fork the sandbox from. Default `main`. |
| `--project ID` | Override `KISENON_PROJECT_ID`. |
| `--max-attempts N` | Max `run_migration` attempts before giving up. Default 5. |
| `--timeout-s N` | Per-command timeout inside the sandbox. Default 300. |
| `--auto-promote` | On green, call `keon sandbox promote` automatically (still parks behind the `human`-mode gate). |
| `--pretty` | Suppress the JSON line; only print the human answer. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | A migration went green on a sandbox. |
| `1` | No green within the attempt budget (`red`), or no attempt made. Best-effort summary still returned. |
| `2` | Fatal error before the loop (missing env, `keon` not on PATH, sandbox feature unavailable). |

## Limitations (v1)

- One request per run. No interactive REPL yet.
- Anthropic + OpenAI only.
- The `human`-mode demo needs `projects.promote_mode = 'human'` set on the
  project. If your build has no CLI/console setter for it yet, set it directly
  (`UPDATE projects SET promote_mode='human' WHERE id='<project-id>'`) and note
  that you did.
- The agent introspects the schema itself via `inspect_schema`; there's no
  pre-loaded data dictionary beyond the compact column summary in the prompt.

## Troubleshooting

### `this keon build has no 'sandbox' command`
Your `keon` predates the sandbox surface. Upgrade/rebuild to a sandbox-enabled
binary and confirm with `keon sandbox --help`.

### `sandboxes are not enabled for this region/project` (`not_implemented` / 501)
The control plane isn't running with the sandbox feature on for this region.
Ask your Kisenon operator to enable it; verify with
`keon sandbox list --project <id> -o json` (should not 501).

### `keon sandbox approve` returns `403`
`approve` is owner/admin only — it's the human side of the gate. Run it as a
project owner, or have one approve the parked sandbox.

### `promote` fails on a `seq` gap
The captured action log is incomplete (a statement wasn't attributed). Re-run
the migration to produce a fresh, complete sandbox, then promote that one.

### `KISENON_PROJECT_ID` / `KISENON_URL` / `ANTHROPIC_API_KEY is not set`
Fill `.env` (or pass `--project <id>`). For `--provider openai`, set
`OPENAI_API_KEY` instead of `ANTHROPIC_API_KEY`.
