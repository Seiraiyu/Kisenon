// Fork main -> apply migrations/002_post_tags.sql on the fork -> serve the fork's
// schema on :5679. Ctrl-C stops the server and deletes the fork (unless --keep).
import { execFileSync, spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import pg from "pg";

const project = process.env.KISENON_PROJECT_ID;
if (!project) {
  console.error("KISENON_PROJECT_ID is not set. See README 'Setup'.");
  process.exit(2);
}
const keep = process.argv.includes("--keep");
const name = `graphql-react-${randomBytes(3).toString("hex")}`;
const keon = (...args) => JSON.parse(execFileSync("keon", [...args, "-o", "json"], { encoding: "utf8" }));

let branchId;
let server;
let cleaned = false;
function cleanup(code) {
  if (cleaned) return;
  cleaned = true;
  server?.kill();
  if (branchId && !keep) {
    try {
      execFileSync("keon", ["branches", "delete", "--cascade", branchId], { stdio: "ignore" });
      console.error(`[fork deleted: ${name}]`);
    } catch {
      console.error(`[cleanup failed: run keon branches delete --cascade ${branchId}]`);
    }
  } else if (branchId) {
    console.error(`[kept: ${name} (${branchId})]`);
  }
  process.exit(code);
}
process.on("SIGINT", () => cleanup(0));
process.on("SIGTERM", () => cleanup(0));

try {
  const started = Date.now();
  branchId = keon("branches", "create", "--project", project, "--name", name,
    "--parent", "main", "--wait").branch.id;
  console.error(`[fork created: ${name} | ${Date.now() - started}ms]`);
  const url = keon("connection-string", name, "--project", project).connection_string;

  const client = new pg.Client({ connectionString: url });
  await client.connect();
  await client.query(readFileSync("migrations/002_post_tags.sql", "utf8"));
  await client.end();
  console.error("[migration applied on fork: 002_post_tags.sql]");

  server = spawn("npx", ["postgraphile", "-C", "graphile.config.mjs"], {
    env: { ...process.env, DATABASE_URL: url, PORT: "5679" },
    stdio: "inherit",
  });
  server.on("exit", (code) => cleanup(code ?? 1));
  console.log("Preview API on http://localhost:5679/graphql");
  console.log("Open http://localhost:5173/?api=fork (main stays at http://localhost:5173/)");
  console.log("Ctrl-C to stop and delete the fork.");
} catch (err) {
  console.error(String(err));
  cleanup(1);
}
