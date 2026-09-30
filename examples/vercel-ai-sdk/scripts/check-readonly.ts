// Proves the read-only guard without an LLM key:  npm run check-readonly
import { runReadOnly, type QueryOutput } from "../lib/readonly";

try {
  process.loadEnvFile(".env");
} catch {
  // variables may come from the shell instead
}

const checks: [string, string, (o: QueryOutput) => boolean][] = [
  ["SELECT works", "SELECT count(*)::int AS orders FROM orders", (o) => "rows" in o],
  [
    "role cannot DELETE",
    "SELECT current_user, has_table_privilege('orders', 'DELETE') AS can_delete",
    (o) => "rows" in o && (o.rows[0] as { can_delete: boolean }).can_delete === false,
  ],
  ["DELETE rejected", "DELETE FROM orders", (o) => "error" in o],
  ["multi-statement rejected", "SELECT 1; DROP TABLE orders", (o) => "error" in o],
  ["5 s timeout", "SELECT pg_sleep(10)", (o) => "error" in o],
];

let ok = true;
for (const [label, sql, pass] of checks) {
  const out = await runReadOnly(sql);
  const good = pass(out);
  ok &&= good;
  console.log(`${good ? "PASS" : "FAIL"}  ${label}: ${JSON.stringify(out)}`);
}
process.exit(ok ? 0 : 1);
