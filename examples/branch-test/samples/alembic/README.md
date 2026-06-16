# Alembic sample

Tiny SQLAlchemy app + three Alembic migrations, sized for the branch-test
demo. The app is intentionally not a real app — there's no FastAPI or
runtime code. The point is the migrations.

## Setup

```bash
cd examples/branch-test/samples/alembic
uv sync
```

## Apply the baseline against main, then load a seed

```bash
# Baseline must exist before either seed can run.
DATABASE_URL="$KISENON_URL" uv run alembic upgrade 001
psql "$KISENON_URL" -f seed/seed_clean.sql      # or seed_dirty.sql
```

## Dry-run the next migrations on a branch

```bash
# From the example root.
cd ../..

uv run branch-test \
  --migrate "uv run alembic upgrade head" \
  --rollback "uv run alembic downgrade base" \
  --working-dir samples/alembic
```

**With seed_clean.sql loaded:** all three migrations apply, rollback
restores the schema, JSON reports `status: green` and the branch is
deleted automatically.

**With seed_dirty.sql loaded:** migration 003 fails on the duplicate
email. JSON reports `status: red`, the failing step's `stderr_tail`
shows the unique violation, and the branch is **preserved** so you
can `psql $branch_url` and inspect.

## Migrations

- `001_create_users.py` — baseline: `users(id, email NOT NULL, name NULL)`.
- `002_backfill_name_not_null.py` — backfill `name`, set NOT NULL.
- `003_add_unique_email.py` — add UNIQUE on `email`. Fails on dirty data.
