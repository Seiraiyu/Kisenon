# rust-sqlx

A ~20-line Rust program that connects to a Kisenon endpoint with
[sqlx](https://github.com/launchbadge/sqlx) 0.9 (tokio + rustls), runs
`SELECT now(), version()`, and exits.

## Run

Requires Rust 1.94+.

```bash
export DATABASE_URL='paste-your-uri-here'   # keon connection-string main --project <id>
cargo run
```

```
now:     2026-09-30 06:17:23.630127 UTC
version: PostgreSQL 17.11 (Kisenon multiver-7b8b6c8-v17) on x86_64-pc-linux-gnu, ...
```

## How it works

- `default-features = false` + `tls-rustls-ring-webpki`: pure-Rust TLS, no OpenSSL.
- `sslmode=require` in the URI is honored; the Kisenon proxy routes by SNI.
- This uses runtime-checked `query_as`. The compile-time `query!` macros also work against Kisenon, since they only need `DATABASE_URL` at build time.
