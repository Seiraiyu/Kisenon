# nodejs-pg

A 20-line Node.js example that connects to a Kisenon endpoint with
[`node-postgres`](https://node-postgres.com), runs `SELECT now()`, and
exits.

## Run

1. Sign in at [kisenon.com](https://kisenon.com), create a project, and
   click **+ New endpoint** on the auto-created `main` branch.
2. Copy the connection URI returned in the dialog.
3. Run:

   ```bash
   export DATABASE_URL='paste-your-uri-here'
   npm install
   npm start
   ```

You should see something like:

```js
{ now: 2026-04-30T14:23:11.412Z,
  version: 'PostgreSQL 17.0 on aarch64-unknown-linux-gnu, ...' }
```

## How it works

- The hostname in the URI is `<endpoint_id>.kisenon.com:5432`.
  The Kisenon proxy parses the SNI server name on the TLS handshake,
  looks up the endpoint, and forwards the connection to the right
  compute pod.
- `sslmode=require` is mandatory — the proxy refuses cleartext.
- The role and password are scoped to that single endpoint. Rotate
  them from the console any time; existing connections keep working
  until they reconnect.
