"""Drive kisenon-mcp over stdio without an AI client: fork, query, explain, diff, destroy.

    uv run python scripts/smoke.py
"""
import asyncio
import json
import os

from mcp import Client, StdioServerParameters


async def call(client: Client, tool: str, args: dict) -> dict:
    result = await client.call_tool(tool, args)
    text = result.content[0].text
    if result.is_error:
        raise SystemExit(f"{tool} failed: {text}")
    data = json.loads(text)
    print(f"{tool}: {json.dumps(data)[:300]}")
    return data


async def main() -> None:
    server = StdioServerParameters(command="uv", args=["run", "kisenon-mcp"], env={**os.environ})
    async with Client(server) as client:
        tools = sorted(t.name for t in (await client.list_tools()).tools)
        print(f"tools: {tools}")
        fork = await call(client, "fork_database", {"name": "smoke"})
        fid = fork["fork_id"]
        await call(client, "run_sql", {"fork_id": fid, "sql": "CREATE TABLE smoke_t (id int)"})
        await call(client, "run_sql", {"fork_id": fid, "sql": "SELECT current_database(), now()"})
        await call(client, "explain_analyze",
                   {"fork_id": fid, "sql": "SELECT count(*) FROM smoke_t"})
        await call(client, "schema_diff", {"fork_id": fid})
        await call(client, "destroy_fork", {"fork_id": fid})
        await call(client, "list_forks", {})


asyncio.run(main())
