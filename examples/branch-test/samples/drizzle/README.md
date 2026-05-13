# Drizzle sample

Tiny Drizzle schema + three hand-written migrations, for the branch-test
demo. The migrations are in `migrations/*.sql` (not generated each time)
so the demo is reproducible.

## Setup

```bash
cd examples/branch-test/samples/drizzle
npm install
```

## Apply baseline against main, then seed

```bash
DATABASE_URL="$KISENON_URL" psql -f migrations/0000_create_users.sql
psql "$KISENON_URL" -f seed/seed_clean.sql      # or seed_dirty.sql
```

## Dry-run remaining migrations on a branch

```bash
cd ../..

uv run branch-test \
  --migrate "npx drizzle-kit migrate" \
  --working-dir samples/drizzle
```

drizzle-kit doesn't ship a single-command "down" migration, so this
sample omits `--rollback`. If you maintain reversible up/down SQL pairs
yourself, pass them via `--rollback "psql -f migrations/down/0002.sql"`.

## Migrations

- `0000_create_users.sql` — baseline.
- `0001_backfill_name_not_null.sql` — backfill + NOT NULL.
- `0002_add_unique_email.sql` — UNIQUE. Fails on `seed_dirty.sql`.
