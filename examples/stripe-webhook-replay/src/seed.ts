// Offline mode: ingest the committed fixture log into main exactly as the webhook server would.
import { readFileSync } from "node:fs";
import type Stripe from "stripe";
import { connect, loadEnv, requireEnv } from "./db";
import { ingest } from "./handler";

loadEnv();
const db = await connect(requireEnv("KISENON_URL"));
const lines = readFileSync(new URL("../fixtures/events.jsonl", import.meta.url), "utf8")
  .trim()
  .split("\n");
let stored = 0;
for (const line of lines) {
  if (await ingest(db, JSON.parse(line) as Stripe.Event)) stored++;
}
await db.end();
process.stderr.write(`[seeded: ${stored} new | duplicates=${lines.length - stored}]\n`);
console.log(JSON.stringify({ deliveries: lines.length, stored, duplicates: lines.length - stored }));
