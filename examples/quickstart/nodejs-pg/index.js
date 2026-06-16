// Minimal Kisenon connection example.
//
// Usage:
//   export DATABASE_URL='postgresql://<role>:<password>@<endpoint_id>.kisenon.com:5432/main?sslmode=require'
//   node index.js
//
// Copy DATABASE_URL from the console — it's the URI returned when you
// click "+ New endpoint" on a branch. The hostname is per-endpoint;
// the kisenon proxy routes by SNI.

import pg from "pg";

const url = process.env.DATABASE_URL;
if (!url) {
  console.error(
    "DATABASE_URL is required. Copy it from kisenon.com → project → branch → endpoint.",
  );
  process.exit(1);
}

const client = new pg.Client({ connectionString: url });

await client.connect();
const { rows } = await client.query("SELECT now() AS now, version()");
console.log(rows[0]);
await client.end();
