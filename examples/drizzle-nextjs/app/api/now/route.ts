// GET /api/now — returns SELECT now() from the configured Kisenon
// endpoint. The pg pool is module-scoped so cold-start cost is paid
// once per Next.js worker.

import { NextResponse } from "next/server";
import pg from "pg";
import { drizzle } from "drizzle-orm/node-postgres";
import { sql } from "drizzle-orm";

export const dynamic = "force-dynamic";

const url = process.env.DATABASE_URL;
if (!url) {
  throw new Error(
    "DATABASE_URL is required — copy it from kisenon.com → endpoint card.",
  );
}

const pool = new pg.Pool({ connectionString: url, max: 5 });
const db = drizzle(pool);

export async function GET() {
  const result = await db.execute(sql`SELECT now() AS now, version()`);
  return NextResponse.json(result.rows[0]);
}
