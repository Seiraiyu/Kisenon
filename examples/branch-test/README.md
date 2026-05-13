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

- A Kisenon project with `main` on it, and the project id handy.
- `keon` CLI, authenticated (`keon login`).
- Postgres 17 client tools (`pg_dump`, `psql`).
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- Your migration tool of choice (this README walks through Alembic and
  Drizzle-kit; the tool works with anything that reads `DATABASE_URL`).

## Quickstart

```bash
cd examples/branch-test

uv sync

cp .env.example .env
# edit .env:
#   KISENON_URL=<your main branch URI>
#   KISENON_PROJECT_ID=<your project id>

# A trivial smoke run — should report green and clean up.
uv run branch-test \
  --migrate "psql \"\$DATABASE_URL\" -c 'SELECT 1'" \
  --pretty
```

The output JSON includes `branch.created_in_ms` so you can confirm
"branches in seconds" against your own infrastructure.

## Walkthrough: Alembic

```bash
cd samples/alembic
uv sync
DATABASE_URL="$KISENON_URL" uv run alembic upgrade 001
psql "$KISENON_URL" -f seed/seed_clean.sql

cd ../..

uv run branch-test \
  --migrate "uv run alembic upgrade head" \
  --rollback "uv run alembic downgrade base" \
  --working-dir samples/alembic \
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

```bash
cd samples/drizzle
npm install
psql "$KISENON_URL" -f migrations/0000_create_users.sql
psql "$KISENON_URL" -f seed/seed_clean.sql

cd ../..

uv run branch-test \
  --migrate "npx drizzle-kit migrate" \
  --working-dir samples/drizzle
```

drizzle-kit doesn't ship a single "down" command; `--rollback` is omitted.
Schema diff is still captured as `before` only; agents can compare the
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
    "created_in_ms": 412,
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

## Limitations (v1)

- No `--promote` flag. (Two-step is the safety checkpoint.)
- No parallel-branches mode. (One run, one branch.)
- No idempotency rerun check. (Run twice yourself; the second run's
  `migrate` step exit code tells you.)
- No lock-impact analysis (which would track `pg_stat_activity` during
  the migrate step).
- pg_dump-based schema diff only — no semantic awareness.
