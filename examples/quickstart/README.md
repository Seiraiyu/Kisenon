# Quickstart examples

Minimal "does Kisenon work with my stack?" examples. Each one is
a single file that opens a connection, runs `SELECT now(), version()`,
prints the result, and exits. The web-framework samples (FastAPI, Django,
Next.js) expose the same query as one HTTP route. Pick whichever matches
your runtime.

| Sample | Stack | Length |
|---|---|---|
| [`nodejs-pg/`](nodejs-pg/) | Node 20+, `node-postgres` (`pg`) | ~30 lines |
| [`python-psycopg/`](python-psycopg/) | Python 3.11+, `psycopg` v3, `uv` | ~25 lines |
| [`drizzle-nextjs/`](drizzle-nextjs/) | Next.js 15 App Router, Drizzle ORM | one `/api/now` route |
| [`go-pgx/`](go-pgx/) | Go 1.25+, `pgx` v5 | ~35 lines |
| [`rust-sqlx/`](rust-sqlx/) | Rust 1.94+, `sqlx` 0.9 (tokio, rustls) | ~20 lines |
| [`prisma/`](prisma/) | Node 20.19+, Prisma 7 + `@prisma/adapter-pg` | ~15 lines |
| [`fastapi-sqlalchemy/`](fastapi-sqlalchemy/) | Python 3.11+, FastAPI + SQLAlchemy 2 + psycopg 3 | one `/now` route |
| [`django/`](django/) | Python 3.12+, Django 6 + dj-database-url | one `/now` view |

## Setup once, run anywhere

All of them read `DATABASE_URL` from the environment. To get one:

1. Sign up at [kisenon.com](https://kisenon.com) (request alpha access
   if you haven't yet — email **alpha@kisenon.com** with subject
   `Alpha access`).
2. Create a project, then click **+ New endpoint** on the `main` branch.
3. Copy the connection URI from the dialog.
4. `export DATABASE_URL='<paste>'`.

Or with the CLI: `export DATABASE_URL="$(keon connection-string main --project <id>)"`.

From there, each sample's README has its own one-line run command.

## What these prove

That a Kisenon endpoint speaks Postgres-on-the-wire. Any `pg`-compatible
driver connects to `<endpoint_id>.kisenon.com:5432` with `sslmode=require`,
the proxy routes by SNI, and you're talking to your branch. No special
driver, no Kisenon SDK.

## What these don't prove

Why you'd pick Kisenon over any other Postgres host. For that, see
[`examples/branch-test`](../branch-test/) — a Python CLI that forks
a Kisenon branch in seconds, runs your migration tool against the
fork, and returns a JSON report an AI agent can read before
promoting the migration to `main`. The branch-per-attempt loop is the
shape of the value prop; these quickstarts are just "yes, your driver
works."
