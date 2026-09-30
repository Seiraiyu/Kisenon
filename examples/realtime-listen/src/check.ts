// End-to-end probe: INSERT -> trigger -> NOTIFY -> (Kisenon proxy) -> LISTEN -> WebSocket.
// Needs `npm start` running in another terminal.
import pg from "pg";
import WebSocket from "ws";
import { parseChange } from "./broadcast.js";

try {
  process.loadEnvFile(".env");
} catch {
  // variables may come from the shell instead
}
const url = process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL is not set (see README 'Setup').");
  process.exit(2);
}
const FALLBACK =
  "No event within 5 s. Check that DATABASE_URL is the direct URI (not '-pooler.'). If NOTIFY " +
  "still doesn't arrive through the proxy, poll instead: SELECT * FROM realtime_listen.items " +
  "WHERE updated_at > $last_seen every second and broadcast the rows.";

const ws = new WebSocket(`ws://localhost:${process.env.PORT ?? 3000}`);
try {
  await new Promise((resolve, reject) => {
    ws.once("open", resolve);
    ws.once("error", reject);
  });
} catch {
  console.error("Can't reach the server. Run `npm start` in another terminal first.");
  process.exit(2);
}

const name = `check-${Date.now()}`;
const arrived = new Promise<number>((resolve) => {
  ws.on("message", (data) => {
    if (parseChange(String(data))?.row.name === name) resolve(Date.now());
  });
});
const timeout = new Promise<null>((resolve) => setTimeout(() => resolve(null), 5000));

const db = new pg.Client({ connectionString: url });
await db.connect();
const started = Date.now();
await db.query("INSERT INTO realtime_listen.items (name, qty) VALUES ($1, 1)", [name]);
const at = await Promise.race([arrived, timeout]);
await db.query("DELETE FROM realtime_listen.items WHERE name = $1", [name]);
await db.end();
ws.close();

if (at === null) {
  console.error(FALLBACK);
  console.log(JSON.stringify({ ok: false }));
  process.exit(2);
}
console.log(`INSERT -> trigger -> NOTIFY -> LISTEN -> WebSocket in ${at - started} ms`);
console.log(JSON.stringify({ ok: true, latency_ms: at - started }));
process.exit(0);
