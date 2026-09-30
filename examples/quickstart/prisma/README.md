# prisma

A minimal [Prisma ORM 7](https://www.prisma.io) script: `$queryRaw` runs
`SELECT now(), version()` against a Kisenon endpoint through the `@prisma/adapter-pg`
driver adapter, then exits. No models needed.

## Run

Requires Node 20.19+.

```bash
export DATABASE_URL='paste-your-uri-here'   # keon connection-string main --project <id>
npm install
npm start
```

```js
OUTPUT_PRISMA
```

## Notes

- Prisma 7 requires a driver adapter; `@prisma/adapter-pg` uses `node-postgres`, which
  connects to Kisenon as-is (`sslmode=require`, SNI routing).
- Versions are pinned to `7.10.0` because `prisma@latest` currently points at an 8.0 release candidate.
- Adding models + migrations: put `datasource: { url: env("DATABASE_URL") }` in
  `prisma.config.ts`, then `npx prisma migrate dev`. Kisenon branches are handy here: run
  migrations against a fork first (see [`branch-test`](../../branch-test/)).
