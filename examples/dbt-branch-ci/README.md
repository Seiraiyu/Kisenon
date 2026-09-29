# dbt-branch-ci

Run `dbt build` on a disposable Kisenon fork of `main`, then compare every
model with `main` — row counts and columns — and fail CI when a change moves
a model's row count past a threshold or breaks its schema. `main` is never
written by the check.

Ships a small jaffle-shop-style dbt project (`jaffle/`: 3 seeds, 3 staging
views, 2 marts), written from scratch for this example.

## Why this needs Kisenon

The usual dbt CI options are a dev schema on the production warehouse (your
PR writes next to prod) or a CI database loaded from a stale dump (row counts
mean nothing). A Kisenon fork is a copy-on-write copy of `main` in seconds:
your changed models build against the exact data they'll see after merge,
and the comparison against `main` is apples to apples. The fork is deleted
when the check ends.

## What you need

- A Kisenon account and project, `keon` CLI logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- Python 3.11+ and [uv](https://docs.astral.sh/uv/). `uv sync` installs
  dbt-core and dbt-postgres.

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `KISENON_PROJECT_ID` | `keon projects list -o json` | required | exits 2: `KISENON_PROJECT_ID is not set` |
| Kisenon auth | `keon login`, or `KEON_API_KEY` (project-scoped `read_write` key) in CI | required | exits 2 with the `keon` error |

No LLM or other third-party keys. The Postgres password is read from `keon
connection-string` at runtime and passed to dbt as `DBT_ENV_SECRET_PASSWORD`,
which dbt scrubs from its logs.

## Setup

```bash
cd examples/dbt-branch-ci
uv sync
cp .env.example .env     # fill KISENON_PROJECT_ID
```

Build the project on `main` once — this stands in for your production dbt
run. Everything lands in the `dbt_branch_ci` schema.

```bash
uv run dbt-branch-ci baseline
```

## Demo 1 — an unchanged project passes

```bash
uv run dbt-branch-ci check
```

```text
[branch forked: dbt-branch-ci-1a2b3c4d | id=...]
[dbt build on dbt-branch-ci-1a2b3c4d]
... dbt output ...
[branch deleted: ...]
model               main    fork    delta  schema
customers             10      10    +0.0%
orders                30      30    +0.0%
raw_customers         10      10    +0.0%
...
PASS
{"passed": true, "failures": [], "branch": {...}, "max_row_delta_pct": 10.0, "models": [...], "total_duration_ms": ...}
```

## Demo 2 — a model change that drops 17% of orders fails

```bash
cp demo/orders.sql jaffle/models/marts/orders.sql    # filters out returned orders
uv run dbt-branch-ci check
echo "exit=$?"
git checkout jaffle/models/marts/orders.sql
```

```text
model               main    fork    delta  schema
customers             10      10    +0.0%
orders                30      25   -16.7%
...
FAIL orders: row count 30 -> 25 (-16.7%, limit 10%)
1 problem(s)
{"passed": false, "failures": ["orders: row count 30 -> 25 (-16.7%, limit 10%)"], ...}
exit=1
```

If the change is intended, raise the limit for this run:
`uv run dbt-branch-ci check --max-row-delta-pct 20`.

## What fails the check

| Change on the fork vs `main` | Result |
|---|---|
| `dbt build` fails (model error or failing data test) | fail |
| a model's row count moves more than `--max-row-delta-pct` (default 10) | fail |
| a column is removed or changes type | fail |
| a model exists on `main` but not on the fork | fail |
| a new model, or a new column | pass (reported) |

## Flags

| Flag | Meaning |
|---|---|
| `--project ID` | Override `KISENON_PROJECT_ID`. |
| `check --max-row-delta-pct N` | Row-count threshold in percent. Default `10`. |
| `check --keep` | Keep the fork for debugging; prints the delete command. |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Build passed, no threshold tripped. |
| `1` | `dbt build` failed or a check failed. |
| `2` | Setup error: missing env, `keon` missing or failing, database unreachable. |

## Using it in CI

Run `uv run dbt-branch-ci check` as a CI step with `KEON_API_KEY` (secret)
and `KISENON_PROJECT_ID` set. Install `keon` in the job with
`curl -fsSL https://kisenon.com/install.sh | KEON_INSTALL_DIR="$HOME/.local/bin" sh`.
See [`gh-actions-preview`](../gh-actions-preview/) for a full GitHub Actions
workflow around the same idea.

## Tests

```bash
uv run pytest       # offline: keon, dbt, and Postgres are mocked
uv run ruff check .
```

## Limitations

- Compares row counts and columns, not values. Add a value-level diff
  (e.g. `dbt-audit-helper`) inside the fork if you need it.
- Every model is rebuilt on the fork — no `state:modified` selection.
  Fine for small projects; add `--select state:modified+` with a
  production manifest for large ones.
- `baseline` writes to `main` on purpose (it's the demo's "production run").
  `check` never writes to `main`.
