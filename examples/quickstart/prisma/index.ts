// Minimal Kisenon connection example (Prisma 7 + driver adapter).
//   export DATABASE_URL='postgresql://<role>:<password>@<endpoint>.kisenon.com:5432/main?sslmode=require'
//   npm start
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "./generated/prisma/client";

const url = process.env.DATABASE_URL;
if (!url) {
  console.error("DATABASE_URL is required. Copy it from kisenon.com -> project -> branch -> endpoint.");
  process.exit(1);
}

const prisma = new PrismaClient({ adapter: new PrismaPg({ connectionString: url }) });
const [row] = await prisma.$queryRaw<{ now: Date; version: string }[]>`SELECT now() AS now, version()`;
console.log({ now: row.now, version: row.version });
await prisma.$disconnect();
