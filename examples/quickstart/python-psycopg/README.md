# python-psycopg

A 25-line Python example that connects to a Kisenon endpoint with
[`psycopg`](https://www.psycopg.org/psycopg3/) (v3), runs
`SELECT now(), version()`, and exits.

## Run

1. Sign in at [kisenon.com](https://kisenon.com), create a project, and
   click **+ New endpoint** on the auto-created `main` branch.
2. Copy the connection URI returned in the dialog.
3. Run:

   ```bash
   export DATABASE_URL='paste-your-uri-here'
   uv sync
   uv run python index.py
   ```

You should see something like:

```python
{'now': '2026-06-16T14:23:11.412000+00:00',
 'version': 'PostgreSQL 17.5 on x86_64-pc-linux-gnu, ...'}
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

## Next

See [`examples/branch-test`](../../branch-test/) for the AI-agent
loop: fork a branch, dry-run a migration on the fork, decide from a
JSON report, and re-apply to `main` only on green.
