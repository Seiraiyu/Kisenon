# drizzle-nextjs

Next.js 15 App Router + Drizzle ORM, with a single `/api/now` route
that runs `SELECT now()` against a Kisenon endpoint.

## Run

1. Sign in at [kisenon.com](https://kisenon.com), create a project, and
   click **+ New endpoint** on the `main` branch.
2. Copy the connection URI from the dialog.
3. Bootstrap:

   ```bash
   export DATABASE_URL='paste-your-uri-here'
   npm install
   npm run dev
   ```

4. Open [http://localhost:3000/api/now](http://localhost:3000/api/now)
   — you should see JSON like
   `{"now": "2026-04-30T...", "version": "PostgreSQL 17.0 ..."}`.

## Schema migrations

This stub doesn't ship a `db/schema.ts`; once you add one, run:

```bash
npm run drizzle:push
```

…to sync the schema to the endpoint via Drizzle Kit.

## How it works

- The pool is module-scoped (`new pg.Pool({...})` at import time) so
  cold-start cost is paid once per Next.js worker.
- The Kisenon proxy resolves `<endpoint_id>.kisenon.com:5432` by SNI;
  no special driver is required — `pg.Pool` and Drizzle work as-is.
- Rotate the password any time from the console. Existing connections
  keep working until they reconnect; replace `DATABASE_URL` in your
  deploy env on the next rollout.
