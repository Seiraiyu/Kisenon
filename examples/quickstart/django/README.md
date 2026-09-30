# django

A single-file Django 6 app (`manage.py` holds settings, URL conf and one view) with
`DATABASES` built from `DATABASE_URL` by [dj-database-url](https://github.com/jazzband/dj-database-url).
`GET /now` runs `SELECT now(), version()`.

## Run

Requires Python 3.12+ (Django 6).

```bash
export DATABASE_URL='paste-your-uri-here'   # keon connection-string main --project <id>
uv sync
uv run python manage.py runserver
curl localhost:8000/now
```

```json
{"now": "2026-09-30T06:17:51.789Z", "version": "PostgreSQL 17.11 (Kisenon multiver-7b8b6c8-v17) on x86_64-pc-linux-gnu, ..."}
```

## Notes

- `ENGINE django.db.backends.postgresql` uses psycopg 3 when it's installed.
- `conn_max_age=600` + `conn_health_checks=True` keep a persistent connection but
  re-check it before use, which suits endpoints that scale to zero.
- In a real project, put the same `DATABASES = {"default": dj_database_url.config(...)}` line in `settings.py`.
