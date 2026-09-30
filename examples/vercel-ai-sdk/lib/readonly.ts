import pg from "pg";

export const ROW_CAP = 100;

// Loose on purpose: pg.PoolClient satisfies it, tests pass a fake, and `queryMode`
// (supported by pg >= 8.x at runtime) is missing from @types/pg.
type Conn = {
  query(q: any): Promise<{ rows: unknown[]; rowCount: number | null }>;
  release(): void;
};

export type QueryOutput =
  | { rows: unknown[]; rowCount: number; truncated: boolean }
  | { error: string };

let pool: pg.Pool | undefined;

function connect(): Promise<Conn> {
  const url = process.env.READONLY_DATABASE_URL;
  if (!url) {
    throw new Error("READONLY_DATABASE_URL is not set (see README 'Create the read-only role').");
  }
  pool ??= new pg.Pool({ connectionString: url, max: 3 });
  return pool.connect();
}

/** One statement, as the SELECT-only role, in a READ ONLY transaction with a 5 s timeout. */
export async function runReadOnly(
  sql: string,
  getConn: () => Promise<Conn> = connect,
): Promise<QueryOutput> {
  const client = await getConn();
  try {
    await client.query("BEGIN READ ONLY");
    await client.query("SET LOCAL statement_timeout = '5s'");
    await client.query("SET LOCAL search_path = vercel_ai_sdk");
    // Extended protocol: Postgres rejects "SELECT 1; DROP TABLE ..." outright.
    const res = await client.query({ text: sql, queryMode: "extended" });
    return {
      rows: res.rows.slice(0, ROW_CAP),
      rowCount: res.rowCount ?? res.rows.length,
      truncated: res.rows.length > ROW_CAP,
    };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  } finally {
    await client.query("ROLLBACK").catch(() => undefined);
    client.release();
  }
}
