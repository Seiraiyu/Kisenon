import type { Config } from "drizzle-kit";

// Drizzle Kit reads DATABASE_URL at CLI time (drizzle-kit push,
// generate, etc). Runtime queries from app/api/* use the same env.
const databaseUrl = process.env.DATABASE_URL;
if (!databaseUrl) {
  throw new Error(
    "DATABASE_URL is required — copy it from kisenon.com → endpoint card.",
  );
}

export default {
  schema: "./db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: { url: databaseUrl },
} satisfies Config;
