# branch-test

Fork your Kisenon `main` branch, run your migration tool against the new
branch, optionally run tests and a rollback, capture the schema diff —
and get a JSON report your AI coding agent can read.

The agent stays in control of the dangerous step: applying the migration
to `main` is the agent's own next call, not a flag on this tool. The
deliberate two-step is the safety checkpoint.

## What this proves about Kisenon

Branches are fast enough that "fork, try, decide, throw away" belongs
inside a normal agent loop. The same workflow against a non-branchable
Postgres would require a backup, a restore, or a separate staging DB
that drifts. Here it's two `keon` calls and a deleted branch.

## What you need

- A Kisenon account with an invite to the alpha. If you don't have one,
  request it: email **alpha@kisenon.com** with subject `Alpha access`,
  or click **Request alpha access** on [kisenon.com](https://kisenon.com).
- The `keon` CLI, installed and logged in. (Setup in the next section.)
- Postgres 17 client tools on your PATH (`pg_dump`, `psql`). On
  Debian/Ubuntu: `sudo apt install postgresql-client-17`. On macOS:
  `brew install postgresql@17`.
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- Your migration tool of choice (this README walks through Alembic and
  Drizzle-kit; the tool works with anything that reads `DATABASE_URL`).

## Sign up & first run

If you're brand-new to Kisenon, this section walks you all the way
from "no account" to "first green run." If you've used `keon` before,
skip to [Quickstart](#quickstart).

### 1. Get into the alpha

Email **alpha@kisenon.com** with subject `Alpha access`, or click
**Request alpha access** on [kisenon.com](https://kisenon.com). Once you
have an invite, sign up at [kisenon.com](https://kisenon.com).

### 2. Install `keon` and log in

```bash
# Linux / macOS
curl -fsSL https://kisenon.com/install.sh | bash

# Windows (PowerShell)
iwr -useb https://kisenon.com/install.ps1 | iex

keon --version          # confirm the install
keon login              # opens your browser for OAuth
```

### 3. Create a project (or use one you already have)

You can create a project from the web UI at [kisenon.com](https://kisenon.com)
→ **Create project**, or note any existing project's id. Then list your
projects from the CLI:

```bash
keon projects list -o json
```

Pick the one you want and copy its `id`.

### 4. Get the connection string for the project's `main` branch

```bash
keon connection-string main --project <project-id> -o json
```

Copy the `connection_string` field — it's a `postgresql://…` URL with an
embedded password. Don't paste it anywhere public.

### 5. Populate `.env`

```bash
cd examples/branch-test
uv sync                 # installs Python deps for branch-test itself
cp .env.example .env
```

Then edit `.env` so it looks like:

```bash
KISENON_PROJECT_ID=<the id from step 3>
KISENON_URL=<the connection_string from step 4>
```

`.env` is already in `.gitignore`. The values feed two things: every
`keon` call gets the project id, and the JSON output's `promote_hint`
shows the agent how to re-run the migration against `main`.

### 6. First green run

```bash
uv run branch-test \
  --migrate "psql \"\$DATABASE_URL\" -c 'SELECT 1'" \
  --pretty
```

You should see a sub-second `branch.created_in_ms`, a green migrate
step, and `branch.deleted: true`. If anything fails, jump to
[Troubleshooting](#troubleshooting).

## Quickstart

For users who already have keon set up and a `.env` in place:

```bash
cd examples/branch-test
uv sync

uv run branch-test \
  --migrate "psql \"\$DATABASE_URL\" -c 'SELECT 1'" \
  --pretty
```

The output JSON includes `branch.created_in_ms` so you can confirm
"branches in seconds" against your own infrastructure.

## Walkthrough: Alembic

> **Heads up:** the sample uses `psycopg` (v3). SQLAlchemy treats a bare
> `postgresql://…` URL as `psycopg2` (legacy) and will error with
> `ModuleNotFoundError: No module named 'psycopg2'`. We use a shell
> rewrite to switch the prefix to `postgresql+psycopg://` for every
> Alembic call. The wrapper passes your URL straight through, so the
> rewrite happens inside the `--migrate` / `--rollback` strings.

```bash
cd samples/alembic
uv sync
# Apply the baseline migration + load 5 distinct users on main.
URL_PSY="$(echo "$KISENON_URL" | sed 's|postgresql://|postgresql+psycopg://|')"
DATABASE_URL="$URL_PSY" uv run alembic upgrade 001
psql "$KISENON_URL" -f seed/seed_clean.sql

cd ../..

uv run branch-test \
  --migrate "DATABASE_URL=\"\$(echo \"\$DATABASE_URL\" | sed 's|postgresql://|postgresql+psycopg://|')\" uv run --directory samples/alembic alembic upgrade head" \
  --rollback "DATABASE_URL=\"\$(echo \"\$DATABASE_URL\" | sed 's|postgresql://|postgresql+psycopg://|')\" uv run --directory samples/alembic alembic downgrade base" \
  --working-dir . \
  --pretty
```

You should see:

- `status: green`
- One step each: `migrate`, `rollback`
- `schema_diff.before_after_unchanged: true`
- `branch.deleted: true`

Now do it again with the dirty seed:

```bash
psql "$KISENON_URL" -f samples/alembic/seed/seed_dirty.sql

uv run branch-test \
  --migrate "uv run alembic upgrade head" \
  --working-dir samples/alembic
```

Migration 003 fails on the duplicate email. JSON:

- `status: red`
- `branch.deleted: false`
- `steps[0].exit_code != 0` with the unique-violation message in
  `stderr_tail`

The branch is preserved at the failed state. `psql $branch_url` shows
the row that would have caused the prod migration to fail.

## Walkthrough: Drizzle-kit

> **Heads up:** don't apply the baseline migration to `main` via raw
> `psql -f …0000_create_users.sql`. drizzle-kit tracks applied
> migrations in its own table (`drizzle.__drizzle_migrations`); if `main`
> has `users` but not the tracker, the forked branch will re-run 0000
> and fail with `relation "users" already exists`. Easiest path: leave
> `main` empty; the wrapper forks an empty branch, and drizzle-kit
> applies all three migrations on that fresh fork.

```bash
cd samples/drizzle
npm install
# Optional: ensure main is empty so drizzle owns the schema on the fork.
psql "$KISENON_URL" -c "DROP TABLE IF EXISTS users CASCADE; DROP SCHEMA IF EXISTS drizzle CASCADE"

cd ../..

uv run branch-test \
  --migrate "npx drizzle-kit migrate" \
  --working-dir samples/drizzle \
  --pretty
```

drizzle-kit doesn't ship a single "down" command; `--rollback` is omitted.
Schema diff is captured as `before` only; agents can compare the
`before` snapshot to `pg_dump main` themselves if they want a real diff.

## And here's the same thing with X

| Tool | `--migrate` value |
|------|-------------------|
| **Prisma** | `npx prisma migrate deploy` |
| **Flyway** | `flyway -url=jdbc:postgresql://... migrate` (use `psql` if you'd rather not pass URL twice) |
| **golang-migrate** | `migrate -database "$DATABASE_URL" -path migrations up` |
| **dbmate** | `dbmate up` |
| **Raw `psql`** | `psql "$DATABASE_URL" -f migrations/0042.sql` |

If the tool reads `DATABASE_URL`, branch-test drives it.

## The agent loop

```
agent has a migration to ship
  │
  ├─ branch-test --migrate "..." --verify "..." --rollback "..."
  │     ↓
  │   JSON
  │     ↓
  ├─ status: red?
  │     → agent reads stderr_tail, fixes migration or seed, retry
  │
  ├─ status: green?
  │     → agent runs the promote_hint.command itself, with $KISENON_URL
  │     → keon branches delete <name>   (optional; auto-delete already cleaned up)
```

The lack of an `--auto-promote` flag is on purpose. The explicit second
call against `main` is the agent's "yes, I confirm" gesture. Add it
yourself in v2 if real usage proves the friction is wrong.

## Output shape

```json
{
  "status": "green",
  "branch": {
    "name": "branch-test-1715634287-ab12",
    "url": "postgresql://...",
    "created_in_ms": 547,
    "deleted": true,
    "delete_skipped_reason": null
  },
  "steps": [
    { "name": "migrate",  "command": "...", "exit_code": 0, "duration_ms": 1843, "stdout_tail": "...", "stderr_tail": "...", "stdout_truncated": false, "stderr_truncated": false },
    { "name": "verify",   "command": "...", "exit_code": 0, "duration_ms": 5210, "...": "..." },
    { "name": "rollback", "command": "...", "exit_code": 0, "duration_ms": 920,  "...": "..." }
  ],
  "schema_diff": {
    "captured": true,
    "before_after_unchanged": true,
    "unified_diff_excerpt": null
  },
  "promote_hint": {
    "next_step": "If this looks right, apply against main:",
    "command": "uv run alembic upgrade head",
    "env": { "DATABASE_URL": "<your KISENON_URL>" }
  }
}
```

## Flags

| Flag | Meaning |
|------|---------|
| `--migrate CMD` (required) | The migration command. Gets `DATABASE_URL` injected. |
| `--verify CMD` | Optional. Runs after migrate. Same env. |
| `--rollback CMD` | Optional. Runs after verify. Same env. |
| `--project ID` | Override `KISENON_PROJECT_ID`. |
| `--name NAME` | Override the auto-generated branch name. |
| `--keep` | Keep the branch even on green. |
| `--delete` | Delete the branch even on red. |
| `--pretty` | Human stdout instead of JSON. |
| `--timeout-s N` | Per-step subprocess timeout. Default 600. |
| `--working-dir PATH` | `cd` here before running each subcommand. |
| `--no-schema-diff` | Skip `pg_dump`. Saves ~1s per run. |

## Troubleshooting

### `psql: error: connection to server … FATAL: endpoint not found`

The Kisenon compute endpoint for your `main` branch went idle (default
suspend after 5 min of no traffic) and the endpoint id baked into your
`KISENON_URL` no longer routes. Fetch a fresh URL and update `.env`:

```bash
keon connection-string main --project "$KISENON_PROJECT_ID" -o json
```

### `ModuleNotFoundError: No module named 'psycopg2'` from Alembic

The `samples/alembic` project depends on `psycopg` (v3) but SQLAlchemy
treats a bare `postgresql://…` URL as `psycopg2`. Rewrite the prefix to
`postgresql+psycopg://` (see the heads-up box in the Alembic
walkthrough above).

### Drizzle: `relation "users" already exists` on the fork

You applied `0000_create_users.sql` to `main` via raw `psql`, but
drizzle-kit's `__drizzle_migrations` tracker doesn't know it ran. The
fork inherits the table *and* the empty tracker, so drizzle-kit re-runs
0000 and the `CREATE TABLE` collides. Either reset `main` empty and let
the fork apply all three migrations, or let drizzle-kit itself apply
0000 to `main` (`DATABASE_URL=$KISENON_URL npx drizzle-kit migrate`)
so the tracker records the revision.

### `keon branches delete` returns `cp 409`

That branch still has an attached compute endpoint. Use `--cascade`:

```bash
keon branches delete --cascade <branch-id>
```

(branch-test already does this for you on green and when `--delete`
is passed.)

### `schema_diff.captured: false`, reason mentions `pg_dump version`

Your local `pg_dump` is older than the server's Postgres version. Fix
by installing `postgresql-client-17` (Debian/Ubuntu) or
`brew install postgresql@17` (macOS). Until then, pass `--no-schema-diff`
to skip the diff step entirely.

### Test branch creation seemed slow

Cold-start latency for the first endpoint after a long idle period can
be several seconds. Subsequent forks reuse a warm compute pool and
typically come back in 500–700 ms; if you're seeing consistent
multi-second forks, file an issue with the run's full JSON output.

## Limitations (v1)

- No `--promote` flag. (Two-step is the safety checkpoint.)
- No parallel-branches mode. (One run, one branch.)
- No idempotency rerun check. (Run twice yourself; the second run's
  `migrate` step exit code tells you.)
- No lock-impact analysis (which would track `pg_stat_activity` during
  the migrate step).
- pg_dump-based schema diff only — no semantic awareness.
