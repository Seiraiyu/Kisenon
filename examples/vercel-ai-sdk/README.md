# vercel-ai-sdk

A Next.js 15 chat app built on the [Vercel AI SDK](https://ai-sdk.dev) (v7). Claude answers
questions about a shop database by calling a `query` tool, and that tool runs SQL on Kisenon
as a **SELECT-only role with a statement timeout**.

## What you need

- Node 22+ (AI SDK 7 is ESM-only and needs Node 22), `psql`, `jq`, `keon` logged in.

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `DATABASE_URL` | `keon connection-string main --project <id>` | setup only | can't load the dataset |
| `READONLY_DATABASE_URL` | built below from `keon roles create` | required | tool calls fail with a clear error |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | required for chat | `/api/chat` returns 500; `npm run check-readonly` still works |

## Setup

```bash
cd examples/vercel-ai-sdk
npm install
cp .env.example .env            # fill DATABASE_URL + ANTHROPIC_API_KEY
set -a; source .env; set +a

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f setup.sql      # schema vercel_ai_sdk: 1k customers, 200 products, 5k orders
```

### Create the read-only role

```bash
PROJECT=<your project id>
MAIN_ID=$(keon branches list --project $PROJECT -o json | jq -r '.branches[] | select(.name=="main") | .id')
keon roles create ai_readonly --branch "$MAIN_ID" -o json > ro.json   # the password is shown only once
jq -r .role.password ro.json                                           # copy it into READONLY_DATABASE_URL, then: rm ro.json
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f readonly.sql
```

`keon roles create` returns `{"operations": [], "role": {"branch_id", "name", "protected", "created_at", "password"}}`.
The role it makes is a normal app role: it can log in, has `CREATEDB`, is a member of
`kisenon_users`, and may `CREATE` in schema `public`. `readonly.sql` takes all of that away
and is the whole policy:

```sql
ALTER ROLE ai_readonly NOCREATEDB;
REVOKE kisenon_users FROM ai_readonly;
REVOKE CREATE ON SCHEMA public FROM ai_readonly;

GRANT USAGE ON SCHEMA vercel_ai_sdk TO ai_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA vercel_ai_sdk TO ai_readonly;
ALTER ROLE ai_readonly SET statement_timeout = '5s';
ALTER ROLE ai_readonly SET default_transaction_read_only = on;
ALTER ROLE ai_readonly SET search_path = vercel_ai_sdk;
```

Set `READONLY_DATABASE_URL` in `.env` to your `DATABASE_URL` with the user and password
replaced: `postgresql://ai_readonly:<password>@<same-host>:5432/main?sslmode=require`.
(Re-running `readonly.sql` is safe; the `REVOKE kisenon_users` line just prints a warning.)

### Check the guard (no LLM key needed)

```bash
npm run check-readonly
```
```
PASS  SELECT works: {"rows":[{"orders":5000}],"rowCount":1,"truncated":false}
PASS  role cannot DELETE: {"rows":[{"current_user":"ai_readonly","can_delete":false}],"rowCount":1,"truncated":false}
PASS  DELETE rejected: {"error":"cannot execute DELETE in a read-only transaction"}
PASS  multi-statement rejected: {"error":"cannot insert multiple commands into a prepared statement"}
PASS  5 s timeout: {"error":"canceling statement due to statement timeout"}
```

`pg` also prints a `SECURITY WARNING` about `sslmode=require` being treated as `verify-full`.
That is expected: Kisenon's certificate verifies, so the stricter mode just works.

## Run

```bash
npm run dev     # http://localhost:3000
```

Try: *"Which product category brought in the most revenue in the last 30 days?"* The UI
shows each `query` call (SQL + rows) as it runs, then the answer.

## How the guard works

1. **Database role**: `ai_readonly` can only `SELECT` from `vercel_ai_sdk`. This is the real boundary.
2. **Per call** (`lib/readonly.ts`): `BEGIN READ ONLY`, `SET LOCAL statement_timeout = '5s'`, run, `ROLLBACK`; at most 100 rows go back to the model.
3. **Extended protocol**: the SQL is sent as a single prepared statement, so `SELECT 1; DROP ...` is rejected by Postgres itself.

## Clean up

```bash
psql "$DATABASE_URL" -c "DROP SCHEMA vercel_ai_sdk CASCADE"
keon roles delete ai_readonly --branch "$MAIN_ID"
```

## Limitations

- No auth on the page; don't deploy it publicly as-is.
- For agents that need to *write*, give them a fork instead: see [`agent-sandbox`](../agent-sandbox/).
