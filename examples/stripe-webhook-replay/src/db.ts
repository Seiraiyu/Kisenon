import pg from "pg";

export const SCHEMA = "stripe_webhook_replay";

export function loadEnv(): void {
  try {
    process.loadEnvFile();
  } catch {
    // No .env file: use the real environment.
  }
}

export function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    process.stderr.write(
      `${JSON.stringify({ error: `${name} is not set.`, hint: "See README#bring-your-own-keys" })}\n`,
    );
    process.exit(2);
  }
  return value;
}

export async function connect(url: string): Promise<pg.Client> {
  const client = new pg.Client({ connectionString: url });
  await client.connect();
  await client.query(`SET search_path TO ${SCHEMA}`);
  return client;
}

/** Pool for the webhook server: one client per request, so transactions don't interleave. */
export function pool(url: string): pg.Pool {
  const p = new pg.Pool({ connectionString: url, max: 5 });
  p.on("connect", (client) => {
    client.query(`SET search_path TO ${SCHEMA}`).catch(() => {});
  });
  return p;
}
