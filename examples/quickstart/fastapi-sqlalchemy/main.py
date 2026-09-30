# Minimal Kisenon connection example (FastAPI + SQLAlchemy 2 + psycopg 3).
#
#   export DATABASE_URL='postgresql://<role>:<password>@<endpoint>.kisenon.com:5432/main?sslmode=require'
#   uv run fastapi run main.py      ->  GET http://localhost:8000/now

import os
import sys

from fastapi import FastAPI
from sqlalchemy import create_engine, make_url, text

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL is required. Copy it from kisenon.com -> project -> branch -> endpoint.")

# postgresql:// -> postgresql+psycopg:// (psycopg 3 driver)
engine = create_engine(make_url(url).set(drivername="postgresql+psycopg"), pool_pre_ping=True)
app = FastAPI()


@app.get("/now")
def now() -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT now() AS now, version() AS version")).one()
    return {"now": row.now, "version": row.version}
