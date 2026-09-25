# graphql-react

A GraphQL API generated from Postgres by [PostGraphile v5](https://postgraphile.org/),
served from Kisenon and used by a Vite + React + [urql](https://commerce.nearform.com/open-source/urql/)
app: an infinite-scroll post feed with voting and a create-post form. The
data model is [lireddit](https://github.com/benawad/lireddit)'s: `users`,
`posts`, and `updoots` (votes), with `posts.points` kept up to date by a
trigger.

Then comes the preview-branch demo. `npm run preview-branch` forks `main`,
adds a `tags` column **on the fork only**, and serves a second API from the
fork. Open the app with `?api=fork` and the tags appear. You changed no
server code, and `main` still has no `tags` column.

This is an integration example ("PostGraphile works on Kisenon"). For
agents working on forks, see [`examples/agent-sandbox`](../agent-sandbox/).

## What you need

- A Kisenon account and project; `keon` CLI installed and logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- Node.js 22.12+ (PostGraphile 5 and Vitest 5 need Node 22) and `psql`.

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `DATABASE_URL` | `keon connection-string main --project <project-id>` | **Required** | The server can't start. |
| `KISENON_PROJECT_ID` | `keon projects list -o json` | Only for `npm run preview-branch` | `preview-branch` exits 2; everything else works. |

No third-party API keys are used.

## Setup

```bash
cd examples/graphql-react
npm install
cp .env.example .env        # fill in DATABASE_URL and KISENON_PROJECT_ID, single-quoted: DATABASE_URL='postgresql://…'
set -a; source .env; set +a
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_schema.sql -f seed.sql
```

That creates the `graphql_react` schema (re-runnable: it drops and recreates
the schema) and seeds 200 users, 2,000 posts and 20,000 votes.

## Run it

```bash
# terminal 1: GraphQL API for main on :5678 (open http://localhost:5678/graphql in a browser for GraphiQL)
npm run server
# terminal 2: the React app on :5173
npm run dev
```

Open http://localhost:5173. Scroll to load more posts, which uses cursor
pagination: `posts(first: 20, after: $cursor, orderBy: [CREATED_AT_DESC, PRIMARY_KEY_DESC])`.
Click ▲/▼ to vote, which calls the `vote` mutation backed by the
`graphql_react.vote()` SQL function. The points come from the trigger.

**Auth is out of scope.** Every post and vote is made by a hard-coded demo
user (`users.id = 1`).

## Preview-branch demo

```bash
# terminal 3 (with terminals 1 and 2 still running)
npm run preview-branch
```

```
[fork created: graphql-react-9c1e2a | 1840ms]
[migration applied on fork: 002_post_tags.sql]
Preview API on http://localhost:5679/graphql
Open http://localhost:5173/?api=fork (main stays at http://localhost:5173/)
Ctrl-C to stop and delete the fork.
```

- http://localhost:5173/?api=fork shows each post's `#tag`.
- http://localhost:5173/ (main) is unchanged: `main` has no `tags` column.
- Ctrl-C stops the preview server and runs `keon branches delete --cascade`
  on the fork. `npm run preview-branch -- --keep` leaves the fork in place.

Vite proxies `/api/main/*` to `:5678` and `/api/fork/*` to `:5679`, so the
app needs no CORS setup.

## Tests

```bash
npm test            # component tests (urql mocked); schema smoke test skipped
npm run typecheck
set -a; source .env; set +a; npm test   # also runs the schema smoke test against DATABASE_URL
```

## Limitations

- No auth, sessions or per-user vote state (`voteStatus` from lireddit is omitted).
- Only posts can be created; there is no edit/delete UI (the mutations exist
  in the API).

## Credits

The schema and domain model are adapted from
[benawad/lireddit](https://github.com/benawad/lireddit), MIT License,
© 2020 Ben Awad. See [`NOTICE`](NOTICE).
