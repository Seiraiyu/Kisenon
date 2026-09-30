# Minimal Kisenon connection example: single-file Django app, DATABASES from DATABASE_URL.
#
#   export DATABASE_URL='postgresql://<role>:<password>@<endpoint>.kisenon.com:5432/main?sslmode=require'
#   uv run python manage.py runserver      ->  GET http://localhost:8000/now

import os
import sys

import dj_database_url
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.urls import path

if not os.environ.get("DATABASE_URL"):
    sys.exit("DATABASE_URL is required. Copy it from kisenon.com -> project -> branch -> endpoint.")

settings.configure(
    DEBUG=True,
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-insecure"),
    ROOT_URLCONF=__name__,
    ALLOWED_HOSTS=["localhost", "127.0.0.1"],
    DATABASES={"default": dj_database_url.config(conn_max_age=600, conn_health_checks=True)},
)


def now(request):
    with connection.cursor() as cur:
        cur.execute("SELECT now(), version()")
        now, version = cur.fetchone()
    return JsonResponse({"now": now, "version": version})


urlpatterns = [path("now", now)]

if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
