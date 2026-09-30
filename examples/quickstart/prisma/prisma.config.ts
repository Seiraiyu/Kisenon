import { defineConfig } from "prisma/config";

// `prisma generate` needs no URL. Add `datasource: { url: env("DATABASE_URL") }` (from
// "prisma/config") once you use `prisma migrate` / `prisma db push`.
export default defineConfig({
  schema: "prisma/schema.prisma",
});
