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
| `KEON_API_KEY` | Kisenon console → Settings → API keys: scope it to the project, capability `agent` (the secret is shown once). The `keon` CLI can't create keys. | Recommended | Falls back to your `keon login` session, which has your full permissions. |
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

`smoke.py` forks, creates a table, queries, explains, diffs and destroys. A real run
(the script cuts long lines at 300 characters):

```
tools: ['destroy_fork', 'explain_analyze', 'fork_database', 'list_forks', 'run_sql', 'schema_diff']
fork_database: {"fork_id": "sbx_fb80ec3c2d", "name": "smoke", "created_at": "2026-09-25T20:47:51+00:00", "expires_at": "2026-09-25T21:17:51+00:00"}
run_sql: {"rows": [], "truncated": false, "rowcount": -1, "duration_ms": 755.5}
run_sql: {"rows": [{"current_database": "main", "now": "2026-09-25 20:47:53.116465+00:00"}], "truncated": false, "rowcount": 1, "duration_ms": 722.5}
explain_analyze: {"plan": "Aggregate  (cost=41.88..41.88 rows=1 width=8) (actual time=0.004..0.005 rows=1 loops=1)\n  ->  Seq Scan on smoke_t  (cost=0.00..35.50 rows=2550 width=0) (actual time=0.002..0.003 rows=0 loops=1)\nPlanning:\n  Buffers: shared hit=25\nPlanning Time: 0.093 ms\nExecution Time: 0.037 ms", "plan
schema_diff: {"blocked_by": null, "capture_current": true, "diff_report": {"format_version": 1, "schema_diff": {"baseline_captured_at": "2026-09-25T20:47:50.018349Z", "database": "main", "changes": [{"kind": "table_added", "table": "smoke_t", "table_def": {"Name": "smoke_t", "Columns": [{"Name": "id", "Type": "i
destroy_fork: {"destroyed": "sbx_fb80ec3c2d"}
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

Recorded with Claude Code (`claude -p`, only the `kisenon-forks` tools enabled;
tool results abbreviated) against a project seeded with
[`examples/agent-sandbox/setup.sql`](../agent-sandbox/setup.sql) (50,000
orders, no index on `orders.customer_id`):

```
> Our homepage runs SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 10.
  Would an index on orders(customer_id, created_at DESC) help? Measure it on a fork, then destroy the fork.

● kisenon-forks - fork_database (name: "orders-index-test")
  ⎿ {"fork_id": "sbx_ff14090211", "expires_at": "2026-09-25T21:18:39+00:00", …}
● kisenon-forks - run_sql (fork_id: "sbx_ff14090211", sql: "SELECT (SELECT count(*) FROM orders) AS total, (SELECT count(*) FROM orders WHERE customer_id=42) AS cust42, …")
  ⎿ {"total": 50000, "cust42": 7, "indexes": "CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (id)"}
● kisenon-forks - explain_analyze (fork_id: "sbx_ff14090211", sql: "SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 10")
  ⎿ Limit -> Sort -> Seq Scan on orders … Rows Removed by Filter: 49993 … Buffers: shared hit=387
    planning_ms: 5.827, execution_ms: 1.52
● kisenon-forks - run_sql (fork_id: "sbx_ff14090211", sql: "CREATE INDEX orders_customer_created_idx ON orders (customer_id, created_at DESC); ANALYZE orders;")
● kisenon-forks - explain_analyze (fork_id: "sbx_ff14090211", sql: "SELECT * FROM orders WHERE customer_id = 42 ORDER BY created_at DESC LIMIT 10")
  ⎿ Limit -> Sort -> Bitmap Heap Scan on orders -> Bitmap Index Scan on orders_customer_created_idx … Buffers: shared hit=9 read=2
    planning_ms: 0.331, execution_ms: 0.317
● kisenon-forks - run_sql (fork_id: "sbx_ff14090211", sql: "SELECT pg_size_pretty(pg_relation_size('orders_customer_created_idx')) AS idx_size, …")
  ⎿ {"idx_size": "1552 kB", "table_size": "3072 kB"}
● kisenon-forks - destroy_fork (fork_id: "sbx_ff14090211")

I measured it on a fork, and yes, the index helps. The fork (`sbx_ff14090211`) is destroyed.

|                           | Before          | After `(customer_id, created_at DESC)` |
|---------------------------|-----------------|----------------------------------------|
| Plan                      | Seq Scan → Sort | Bitmap Index Scan → Sort               |
| Rows read and thrown away | 49,993          | 0                                      |
| Buffers touched           | 387             | 11                                     |
| Execution time            | 1.52 ms         | 0.32 ms                                |

The `created_at` part of the index wasn't used here: customer 42 has only 7 orders, so
Postgres just sorted them. The second column is what lets Postgres skip the sort and stop
after 10 rows for customers with many orders. … To add it in production without blocking writes:
CREATE INDEX CONCURRENTLY orders_customer_created_idx ON orders (customer_id, created_at DESC);
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
