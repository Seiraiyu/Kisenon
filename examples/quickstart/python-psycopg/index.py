# Minimal Kisenon connection example.
#
# Usage:
#   export DATABASE_URL='postgresql://<role>:<password>@<endpoint_id>.kisenon.com:5432/main?sslmode=require'
#   uv sync
#   uv run python index.py
#
# Copy DATABASE_URL from the console — it's the URI returned when you
# click "+ New endpoint" on a branch. The hostname is per-endpoint;
# the kisenon proxy routes by SNI.

import os
import sys

import psycopg

url = os.environ.get("DATABASE_URL")
if not url:
    print(
        "DATABASE_URL is required. Copy it from kisenon.com -> project -> branch -> endpoint.",
        file=sys.stderr,
    )
    sys.exit(1)

with psycopg.connect(url) as conn, conn.cursor() as cur:
    cur.execute("SELECT now() AS now, version()")
    now, version = cur.fetchone()
    print({"now": now.isoformat(), "version": version})
