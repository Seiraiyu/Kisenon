# gh-actions-preview

A GitHub Actions workflow that gives every pull request its own Kisenon
branch. On open/push it forks `main` as `pr-<number>`, runs your migrations
and tests against the fork, and posts one sticky PR comment with the results,
the schema diff vs `main`, and a password-free connection hint. When the PR
closes, the branch is deleted.

The workflow lives in this directory (not in this repo's `.github/`) — you
copy it into your own repo.

## Why this needs Kisenon

A shared staging database means PRs trample each other's schema; a
throwaway Postgres container per PR means testing migrations against an
empty database. A Kisenon branch is a copy-on-write fork of `main` — real
schema, real data — created in seconds, reset to `main` on every push, and
suspended when idle. Your migration is proven against production-shaped data
before it merges, and `main` is never written by CI.

## What you need

- A Kisenon account and project, and the `keon` CLI for the one-time setup
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- A GitHub repo where you can add Actions secrets and variables, and the
  [`gh` CLI](https://cli.github.com/) (optional, used below).
- `psql` to apply your existing migrations to `main` once.

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `KEON_API_KEY` (repo **secret**) | `keon api-keys create --scope project --capability read_write` (see Setup) | required | the fork step fails because `keon` is not authenticated; no comment is posted |
| `KISENON_PROJECT_ID` (repo **variable**) | `keon projects list -o json` | required | the fork step exits 2: `KISENON_PROJECT_ID is not set` |
| `GITHUB_TOKEN` | provided by Actions | automatic | — |

Use a **project-scoped `read_write`** key. An `agent`-capability key cannot
read connection URIs, and CI needs `DATABASE_URL` to run migrations.

## Setup (in your repo)

```bash
# 1. Copy the workflow, the script it calls, and the demo migrations.
cp -r path/to/examples/gh-actions-preview/{.github,scripts,db} .

# 2. Apply the migrations already merged to main, once.
psql "$(keon connection-string main --project "$KISENON_PROJECT_ID")" \
  -v ON_ERROR_STOP=1 -f db/migrations/001_create_todos.sql

# 3. Create a project-scoped key; the secret is printed once.
keon api-keys create --name gh-preview --scope project \
  --scope-id "$KISENON_PROJECT_ID" --capability read_write -o table
gh secret set KEON_API_KEY          # paste the nsk_... secret when prompted
gh variable set KISENON_PROJECT_ID --body "$KISENON_PROJECT_ID"

# 4. Commit and push to main.
git add .github scripts db
git commit -m "Add Kisenon preview branches"
git push
```

## Demo

Open a PR that adds a migration:

```bash
git checkout -b add-due-date
cp path/to/examples/gh-actions-preview/demo/002_add_due_date.sql db/migrations/
git add db/migrations && git commit -m "Add todos.due_date"
git push -u origin add-due-date
gh pr create --fill
gh pr checks --watch
gh pr view --comments
```

The `kisenon-preview` check goes green and the PR gets one comment:

````markdown
## Kisenon preview branch `pr-1`

Forked from `main` on every push to this PR.

| Step | Result |
|---|---|
| Migrations | success |
| Tests | success |

<details><summary>Schema diff vs main</summary>

```json
{ ...keon branches schema-diff output: due_date column + index... }
```

</details>

Connect (password not shown):

```
postgresql://<role>:****@<endpoint>.kisenon.com:5432/main?sslmode=require
keon connection-string pr-1 --project $KISENON_PROJECT_ID
```

The branch is deleted when this PR is closed.
````

Now push a breaking migration to the same PR:

```bash
cp path/to/examples/gh-actions-preview/demo/003_drop_title.sql db/migrations/
git add db/migrations && git commit -m "Drop todos.title" && git push
gh pr checks --watch     # fails: db/test.sql inserts into todos(title)
```

`pr-1` is reset to `main` and every migration re-runs; the same comment
updates to `Tests | failure`. Close the PR (`gh pr close --delete-branch`)
and the `cleanup` job deletes `pr-1` and marks the comment as deleted.

## How it works

| File | Role |
|---|---|
| `.github/workflows/kisenon-preview.yml` | `preview` job on open/reopen/push; `cleanup` job on close. Installs `keon` with the install script; `keon` reads `KEON_API_KEY` from the env. |
| `scripts/kisenon_preview.py` | Stdlib-only helper: `up` (create or reset `pr-<n>`, export masked `DATABASE_URL`), `comment` (render the comment), `down` (delete, no-op if gone). |
| `db/migrations/*.sql` | Applied in filename order on the fork. Idempotent, because the fork already has everything merged to `main`. |
| `db/test.sql` | A smoke test. Replace with your real test command. |
| `demo/*.sql` | Migrations for the demo PR. |

The comment is posted with
[`marocchino/sticky-pull-request-comment`](https://github.com/marocchino/sticky-pull-request-comment)
(header `kisenon-preview`), so each push edits the same comment. Pin it to a
commit SHA if your org requires that.

## Adapting it

- Replace **Run migrations** with your tool (`alembic upgrade head`,
  `npx prisma migrate deploy`, `sqitch deploy`, ...) using `$DATABASE_URL`.
- Replace **Run tests** with your suite; it gets the same `$DATABASE_URL`.
- Keep the **Build PR comment** step's `--migrations`/`--tests` wired to
  your steps' `id`s.

## Run the script locally

```bash
cp .env.example .env    # fill KISENON_PROJECT_ID
set -a; source .env; set +a
export DATABASE_URL="$(python3 scripts/kisenon_preview.py up --pr 999)"
python3 scripts/kisenon_preview.py comment --pr 999 --out /dev/stdout
python3 scripts/kisenon_preview.py down --pr 999
```

Exit codes: `0` ok, `1` a `keon` call failed, `2` setup error (missing
`KISENON_PROJECT_ID`, `keon` not installed).

## Tests

```bash
uv sync
uv run pytest     # offline: keon is mocked
uv run ruff check .
```

## Limitations

- PRs from **forks** don't receive repo secrets, so the preview job fails
  for them. Don't switch to `pull_request_target` to work around it — that
  runs untrusted code with your key.
- One branch per open PR. Idle branches suspend their compute, but they
  still count toward your project's branch limit.
- The schema diff is the changed lines (and their `TABLE` header) from
  `keon branches schema-diff`, truncated at 50,000 characters. If `main`'s compute can't be woken in time, the comment says
  `schema diff unavailable` and the job still reports tests normally.
