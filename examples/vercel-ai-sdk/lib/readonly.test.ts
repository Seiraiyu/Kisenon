import { expect, it } from "vitest";
import { ROW_CAP, runReadOnly } from "./readonly";

function fake(result: { rows: unknown[]; rowCount: number | null } | Error) {
  const sent: unknown[] = [];
  let released = false;
  const conn = {
    async query(q: any) {
      sent.push(q);
      if (typeof q === "object") {
        if (result instanceof Error) throw result;
        return result;
      }
      return { rows: [], rowCount: null };
    },
    release() {
      released = true;
    },
  };
  return { sent, conn, released: () => released };
}

it("wraps the statement in a read-only transaction with a timeout, then rolls back", async () => {
  const f = fake({ rows: [{ n: 1 }], rowCount: 1 });
  const out = await runReadOnly("SELECT 1 AS n", async () => f.conn);
  expect(out).toEqual({ rows: [{ n: 1 }], rowCount: 1, truncated: false });
  expect(f.sent).toEqual([
    "BEGIN READ ONLY",
    "SET LOCAL statement_timeout = '5s'",
    "SET LOCAL search_path = vercel_ai_sdk",
    { text: "SELECT 1 AS n", queryMode: "extended" },
    "ROLLBACK",
  ]);
  expect(f.released()).toBe(true);
});

it("caps rows sent back to the model", async () => {
  const rows = Array.from({ length: ROW_CAP + 5 }, (_, i) => ({ i }));
  const out = await runReadOnly("SELECT i", async () => fake({ rows, rowCount: rows.length }).conn);
  expect(out).toMatchObject({ rowCount: ROW_CAP + 5, truncated: true });
  expect("rows" in out && out.rows.length).toBe(ROW_CAP);
});

it("returns database errors to the model instead of throwing, and still releases", async () => {
  const f = fake(new Error("permission denied for table orders"));
  const out = await runReadOnly("DELETE FROM orders", async () => f.conn);
  expect(out).toEqual({ error: "permission denied for table orders" });
  expect(f.sent.at(-1)).toBe("ROLLBACK");
  expect(f.released()).toBe(true);
});
