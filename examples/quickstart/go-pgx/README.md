# go-pgx

A ~35-line Go program that connects to a Kisenon endpoint with
[pgx v5](https://github.com/jackc/pgx), runs `SELECT now(), version()`, and exits.

## Run

Requires Go 1.25+ (older Go downloads the toolchain automatically).

```bash
export DATABASE_URL='paste-your-uri-here'   # keon connection-string main --project <id>
go run .
```

```
now:     2026-09-30T02:17:09.061063-04:00
version: PostgreSQL 17.11 (Kisenon multiver-7b8b6c8-v17) on x86_64-pc-linux-gnu, ...
```

## How it works

- pgx parses the `postgresql://` URI directly; `sslmode=require` is honored.
- The Kisenon proxy routes by the TLS SNI hostname (`<endpoint>.kisenon.com`), so no special driver config is needed.
- For an app, use `pgxpool.New(ctx, url)` instead of a single `pgx.Connect`.
