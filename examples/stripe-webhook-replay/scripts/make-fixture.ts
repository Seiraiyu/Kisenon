import { writeFileSync } from "node:fs";
import { buildEvents } from "../src/fixture";

const events = buildEvents();
writeFileSync(
  new URL("../fixtures/events.jsonl", import.meta.url),
  events.map((e) => JSON.stringify(e)).join("\n") + "\n",
);
process.stderr.write(`[wrote: ${events.length} events | fixtures/events.jsonl]\n`);
