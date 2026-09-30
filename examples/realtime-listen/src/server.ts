import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import pg from "pg";
import { WebSocketServer } from "ws";
import { broadcast, parseChange } from "./broadcast.js";

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
if (url.includes("-pooler.")) {
  console.error("[warning: DATABASE_URL is a pooled URI; LISTEN needs the direct one]");
}
const port = Number(process.env.PORT ?? 3000);
const page = readFileSync(new URL("../public/index.html", import.meta.url));

const http = createServer((req, res) => {
  if (req.url === "/") {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" }).end(page);
  } else {
    res.writeHead(404).end();
  }
});
const wss = new WebSocketServer({ server: http });

// One long-lived session connection. LISTEN is per-session, so no pool here.
const db = new pg.Client({ connectionString: url, keepAlive: true });
db.on("notification", (msg) => {
  const change = parseChange(msg.payload);
  if (!change) return;
  const sent = broadcast(wss.clients, JSON.stringify(change));
  console.error(`[notify: ${change.op} ${change.table} id=${String(change.row.id)} | clients=${sent}]`);
});
// ponytail: exit on connection loss and let a supervisor restart; production code should
// reconnect with backoff and re-sync missed rows (e.g. WHERE updated_at > last_seen).
const die = (why: string) => {
  console.error(`[listen connection lost: ${why}]`);
  process.exit(1);
};
db.on("error", (err) => die(err.message));
db.on("end", () => die("ended"));

await db.connect();
await db.query("LISTEN realtime_listen");
http.listen(port, () =>
  console.error(`[listening: http://localhost:${port} | channel=realtime_listen]`),
);
