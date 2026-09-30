# fastapi-sqlalchemy

One FastAPI route, `GET /now`, that runs `SELECT now(), version()` on a Kisenon endpoint
via SQLAlchemy 2 and psycopg 3.

## Run

```bash
export DATABASE_URL='paste-your-uri-here'   # keon connection-string main --project <id>
uv sync
uv run fastapi run main.py
curl localhost:8000/now
```

```json
{"now":"2026-09-30T06:17:49.802443Z","version":"PostgreSQL 17.11 (Kisenon multiver-7b8b6c8-v17) on x86_64-pc-linux-gnu, ..."}
```

## Notes

- `make_url(url).set(drivername="postgresql+psycopg")` selects psycopg 3; the rest of the
  URI (including `sslmode=require`) passes through unchanged.
- `pool_pre_ping=True` transparently replaces connections dropped while the endpoint
  was scaled down.
