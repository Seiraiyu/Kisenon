# realtime-listen

Live row changes in the browser with nothing but Postgres and ~60 lines of Node:

```
UPDATE items ... ─► trigger ─► pg_notify('realtime_listen', json)
                                   │  (Kisenon proxy, session connection)
                                   ▼
                     Node `pg` client: LISTEN realtime_listen
                                   │
                                   ▼  ws broadcast
                              browser table
```

## What you need

- Node 20.12+, `psql`, a Kisenon project (`keon login`).

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `DATABASE_URL` | `keon connection-string main --project <id>` (**not** `--pooled`) | required | exits 2 |

No API keys needed.

## Setup

```bash
cd examples/realtime-listen
npm ci
cp .env.example .env    # set DATABASE_URL (direct URI)
psql "$(grep ^DATABASE_URL .env | cut -d= -f2-)" -v ON_ERROR_STOP=1 -f setup.sql
```

## Run

```bash
npm start                 # terminal 1 -> open http://localhost:3000
npm run check             # terminal 2: end-to-end probe
```
```
INSERT -> trigger -> NOTIFY -> LISTEN -> WebSocket in 49 ms
{"ok":true,"latency_ms":49}
```

Then change rows by hand and watch the page:

```sql
INSERT INTO realtime_listen.items (name, qty) VALUES ('widget', 3);
UPDATE realtime_listen.items SET qty = qty + 1, updated_at = now() WHERE name = 'widget';
DELETE FROM realtime_listen.items WHERE name = 'widget';
```

Server log (the first two `notify` lines are from `npm run check`; with the page open,
`clients` is 1 or more):
```
[listening: http://localhost:3000 | channel=realtime_listen]
[notify: INSERT items id=1 | clients=1]
[notify: DELETE items id=1 | clients=1]
[notify: INSERT items id=2 | clients=0]
[notify: UPDATE items id=2 | clients=0]
[notify: DELETE items id=2 | clients=0]
```

## Things to know

- **Session connection required.** `LISTEN` belongs to one session. Use the direct URI; a
  transaction-mode pooler (`-pooler.` host) won't deliver notifications. The server warns if
  it sees one.
- **Notifications fire on commit**, in commit order; a rolled-back transaction sends nothing.
- **8000-byte payload limit.** For wide rows, send only the id and let clients fetch.
- **Not a durable log.** If the listener is disconnected, events in that window are lost.
  On reconnect, re-sync with `WHERE updated_at > <last seen>`. This demo just exits on
  connection loss.
- **Idle connections survive.** Tested on Kisenon (2026-09-30): the `LISTEN` session sat idle
  for about 11 minutes through the proxy, and the next `npm run check` still passed (45 ms).
  Longer idle periods were not tested. If a proxy or NAT does drop the connection, the server
  logs `[listen connection lost: ...]` and exits 1.
- **Fallback if NOTIFY can't reach you:** poll `realtime_listen.items` by `updated_at` every
  second and broadcast the diff; the page doesn't change.
- `pg` prints a one-time `SECURITY WARNING` about `sslmode=require` being treated as
  `verify-full`. That is the stricter mode, and it works with Kisenon's certificate.
