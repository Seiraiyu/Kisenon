"""Live demo: each test gets the fixture's data; destructive tests don't leak.

  uv run pytest demo_tests -v                             # forks fixture-small
  uv run pytest demo_tests -v --kisenon-fixture prodlike
"""
import psycopg


def count(url: str, table: str) -> int:
    with psycopg.connect(url) as conn:
        return conn.execute(f"SELECT count(*) FROM seed_snapshots.{table}").fetchone()[0]


def test_delete_every_order(kisenon_db):
    with psycopg.connect(kisenon_db) as conn:
        conn.execute("DELETE FROM seed_snapshots.orders")
    assert count(kisenon_db, "orders") == 0


def test_orders_are_back_after_reset(kisenon_db):
    assert count(kisenon_db, "orders") > 0, "reset should restore the fixture's orders"


def test_drop_users_table(kisenon_db):
    with psycopg.connect(kisenon_db) as conn:
        conn.execute("DROP TABLE seed_snapshots.users CASCADE")


def test_users_are_back_after_reset(kisenon_db):
    assert count(kisenon_db, "users") > 0
