// Fork main, rebuild the projections on the fork from the event log with the handler
// code on disk, and diff main vs fork. Exit 0 identical, 1 differ, 2 fatal.
import { randomUUID } from "node:crypto";
import { parseArgs } from "node:util";
import type Stripe from "stripe";
import { connect, loadEnv, requireEnv } from "./db";
import { diffRows, type RowDiff } from "./diff";
import { applyEvent } from "./handler";
import { type Branch, branchUrl, createFork, deleteBranch } from "./keon";

const PROJECTIONS = [
  { table: "users", key: "stripe_id", sql: "SELECT stripe_id, email, type FROM users ORDER BY stripe_id" },
  {
    table: "subscriptions",
    key: "id",
    sql: `SELECT id, customer, status, price_id, current_period_end, cancel_at_period_end
          FROM subscriptions ORDER BY id`,
  },
];

const log = (msg: string) => process.stderr.write(`[${msg}]\n`);

async function main(): Promise<number> {
  loadEnv();
  const { values } = parseArgs({
    options: {
      keep: { type: "boolean", default: false },
      pretty: { type: "boolean", default: false },
      project: { type: "string" },
    },
  });
  const project = values.project ?? requireEnv("KISENON_PROJECT_ID");
  const mainUrl = requireEnv("KISENON_URL");

  let fork: Branch | undefined;
  const cleanup = () => {
    if (!fork || values.keep) return;
    const id = fork.id;
    fork = undefined;
    try {
      deleteBranch(id);
      log(`branch deleted: ${id}`);
    } catch (e) {
      log(`cleanup failed: ${(e as Error).message} | run: keon branches delete --cascade ${id}`);
    }
  };
  process.once("SIGINT", () => { cleanup(); process.exit(130); });
  process.once("SIGTERM", () => { cleanup(); process.exit(143); });

  try {
    const started = Date.now();
    fork = createFork(project, `stripe-webhook-replay-${randomUUID().slice(0, 8)}`);
    const name = fork.name;
    const id = fork.id;
    log(`branch forked: ${name} | ${Date.now() - started}ms`);
    const mainDb = await connect(mainUrl);
    const forkDb = await connect(branchUrl(project, name));
    try {
      await forkDb.query("TRUNCATE users, subscriptions RESTART IDENTITY");
      const { rows } = await forkDb.query<{ payload: Stripe.Event }>(
        "SELECT payload FROM stripe_events ORDER BY created, id",
      );
      for (const r of rows) await applyEvent(forkDb, r.payload);
      log(`replayed: ${rows.length} events`);

      const diffs: Record<string, RowDiff[]> = {};
      for (const p of PROJECTIONS) {
        diffs[p.table] = diffRows((await mainDb.query(p.sql)).rows, (await forkDb.query(p.sql)).rows, p.key);
      }
      const changed = Object.values(diffs).reduce((n, d) => n + d.length, 0);

      console.log(`Replayed ${rows.length} events on ${name} with the handler on disk.`);
      for (const [table, d] of Object.entries(diffs)) {
        console.log(d.length === 0 ? `${table}: identical` : `${table}: ${d.length} rows differ`);
        for (const x of d) {
          console.log(`  ${x.key}: main=${JSON.stringify(x.main)} fork=${JSON.stringify(x.fork)}`);
        }
      }
      if (!values.pretty) {
        console.log(JSON.stringify({
          branch: { name, id, kept: values.keep }, events: rows.length, changed, diffs,
        }));
      }
      return changed === 0 ? 0 : 1;
    } finally {
      await mainDb.end();
      await forkDb.end();
    }
  } catch (e) {
    process.stderr.write(`${JSON.stringify({ error: e instanceof Error ? e.message : String(e) })}\n`);
    return 2;
  } finally {
    cleanup();
  }
}

process.exitCode = await main();
