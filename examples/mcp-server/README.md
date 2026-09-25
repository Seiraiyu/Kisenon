# mcp-server

An [MCP](https://modelcontextprotocol.io) server that gives Claude Code,
Cursor or Claude Desktop **disposable forks of your Postgres database** as
native tools. Your assistant can fork `main`, run whatever SQL it needs
(including `DELETE`, `ALTER` and `CREATE INDEX`), measure with
`EXPLAIN ANALYZE`, show you the schema diff, and throw the fork away.

| Tool | What it does |
|---|---|
| `fork_database(name?)` | Fork `main` into a scoped sandbox. Returns `{fork_id, expires_at}`. |
| `run_sql(fork_id, sql)` | Any SQL on the fork. Up to 200 rows, plus the rowcount and duration. |
| `explain_analyze(fork_id, sql)` | `EXPLAIN (ANALYZE, BUFFERS)` plan text, planning ms and execution ms. |
| `schema_diff(fork_id)` | Schema and data changes on the fork vs `main` (`keon sandbox diff`). |
| `destroy_fork(fork_id)` | Delete the fork now. |
| `list_forks()` | Forks this server created that are still alive. |

Built on the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
v2 (`MCPServer`, formerly `FastMCP`), stdio transport.

## Why this needs Kisenon

"Would this index help?" and "what would this migration break?" can only be
answered honestly by *running* the change against real data. Pointing an
assistant at production for that is unacceptable, and a staging copy drifts.
Each `fork_database` call is a copy-on-write fork of `main` in seconds, and
`main` can't be reached at all:

- **No tool accepts a connection string.** Every SQL tool takes a `fork_id`,
  and the server only accepts ids it created in this session. Anything else,
  including `"main"`, is refused.
- **Scoped sandbox credentials.** Forks are made with `keon sandbox create`,
  which returns a credential for the fork only.
- **Forks expire.** Each fork has a wall-clock budget of
  `KISENON_FORK_TTL_MIN` (default 30 minutes) enforced by Kisenon. The server
  also reaps expired forks on every tool call and destroys all of its forks on
  shutdown.

## What you need

- A Kisenon account and project; the `keon` CLI on `PATH`
  (`curl -fsSL https://kisenon.com/install.sh | bash`).
- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- An MCP client: Claude Code, Cursor or Claude Desktop.

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `KEON_API_KEY` | `keon api-keys create --name mcp-forks --scope project --scope-id <project-id> --capability agent` (the secret is printed once) | Recommended | Falls back to your `keon login` session, which has your full permissions. |
| `KISENON_PROJECT_ID` | `keon projects list -o json` | Recommended | `keon`'s default project from `keon set-context` is used. |

An `agent`-capability key can create and use sandboxes but can't read
connection URIs for `main`, rotate passwords, or manage branch roles. That's
the right blast radius for a tool an LLM drives. No LLM API key is needed:
the MCP client brings the model.

## Setup

```bash
cd examples/mcp-server
uv sync
uv run python scripts/smoke.py   # optional: exercise every tool once, no AI client needed
```

`smoke.py` forks, creates a table, queries, explains, diffs and destroys:

```
tools: ['destroy_fork', 'explain_analyze', 'fork_database', 'list_forks', 'run_sql', 'schema_diff']
fork_database: {"fork_id": "…", "name": "smoke", "created_at": "…", "expires_at": "…"}
run_sql: {"rows": [], "truncated": false, "rowcount": -1, "duration_ms": …}
run_sql: {"rows": [{"current_database": "…", "now": "…"}], "truncated": false, "rowcount": 1, "duration_ms": …}
explain_analyze: {"plan": "Aggregate  (…)\n  ->  Seq Scan on smoke_t …", "planning_ms": …, "execution_ms": …}
schema_diff: {…}
destroy_fork: {"destroyed": "…"}
list_forks: {"forks": []}
```

## Add it to your client

Replace `/ABSOLUTE/PATH/TO` with where you cloned this repo.

**Claude Code:**

```bash
claude mcp add kisenon-forks -e KEON_API_KEY=<your-agent-key> -e KISENON_PROJECT_ID=<project-id> -- uv --directory /ABSOLUTE/PATH/TO/examples/mcp-server run kisenon-mcp
```

**Cursor** (`~/.cursor/mcp.json`) and **Claude Desktop**
(`claude_desktop_config.json`, via Settings → Developer → Edit Config) use
the same entry:

```json
{
  "mcpServers": {
    "kisenon-forks": {
      "command": "uv",
      "args": ["--directory", "/ABSOLUTE/PATH/TO/examples/mcp-server", "run", "kisenon-mcp"],
      "env": { "KEON_API_KEY": "<your-agent-key>", "KISENON_PROJECT_ID": "<project-id>" }
    }
  }
}
```

## Transcript: "would this index help?"

Recorded with Claude Code against a project seeded with
[`examples/agent-sandbox/setup.sql`](../agent-sandbox/setup.sql) (50,000
orders, no index on `orders.customer_id`):

```
> Our homepage runs SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 10.
  Would an index on orders(customer_id, created_at DESC) help? Measure it on a fork.

● kisenon-forks - fork_database (name: "orders-index")
● kisenon-forks - explain_analyze (fork_id: "…", sql: "SELECT * FROM orders WHERE customer_id = 42 …")
  ⎿ Seq Scan on orders … Execution Time: … ms
● kisenon-forks - run_sql (fork_id: "…", sql: "CREATE INDEX ON orders (customer_id, created_at DESC)")
● kisenon-forks - explain_analyze (…)
  ⎿ Index Scan using orders_customer_id_created_at_idx … Execution Time: … ms
● kisenon-forks - destroy_fork (fork_id: "…")

Yes: … ms → … ms (…× faster) …
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `KEON_API_KEY` | (your `keon login`) | Credential `keon` uses. |
| `KISENON_PROJECT_ID` | (`keon set-context`) | Project whose `main` is forked. |
| `KISENON_FORK_TTL_MIN` | `30` | Fork lifetime in minutes. |

## Limitations

- Forks are sandboxes (`keon sandbox create`), so sandbox budgets apply: a
  fork is auto-discarded if it exceeds the project's statement or compute
  budget.
- `run_sql` opens a new connection per call; session state such as `SET` or
  temp tables does not carry over between calls.
- Results are capped at 200 rows.
- Forks are tracked in memory. If the server is killed with `SIGKILL`, its
  forks still expire server-side after their TTL.
