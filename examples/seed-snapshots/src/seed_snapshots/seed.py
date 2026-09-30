"""The demo schema and its three fixture sizes, seeded server-side.

generate_series is the fastest re-seed there is, so the timing comparison is a
lower bound: factory-based seeding in a real test suite is slower still.
"""
from __future__ import annotations

SCHEMA = "seed_snapshots"

FIXTURES: dict[str, tuple[int, int]] = {  # name -> (users, orders)
    "empty": (0, 0),
    "small": (100, 1_000),
    "prodlike": (100_000, 1_000_000),
}

DDL = """
DROP SCHEMA IF EXISTS seed_snapshots CASCADE;
CREATE SCHEMA seed_snapshots;
CREATE TABLE seed_snapshots.users (
  id         bigint PRIMARY KEY,
  email      text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL
);
CREATE TABLE seed_snapshots.orders (
  id          bigint PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES seed_snapshots.users (id),
  total_cents integer NOT NULL,
  status      text NOT NULL,
  created_at  timestamptz NOT NULL
);
CREATE INDEX orders_user_id_idx ON seed_snapshots.orders (user_id);
"""

USERS_SQL = """
INSERT INTO seed_snapshots.users (id, email, created_at)
SELECT g, 'user' || g || '@example.com', now() - g * interval '1 minute'
FROM generate_series(1, %(users)s) AS g
"""

ORDERS_SQL = """
INSERT INTO seed_snapshots.orders (id, user_id, total_cents, status, created_at)
SELECT g,
       1 + g %% %(users)s,
       (g * 37) %% 10000,
       (ARRAY['placed', 'shipped', 'completed', 'returned'])[1 + g %% 4],
       now() - g * interval '1 second'
FROM generate_series(1, %(orders)s) AS g
"""


def seed(conn, fixture: str) -> None:
    """Drop and recreate the demo schema on `conn`, then fill it to `fixture` size."""
    users, orders = FIXTURES[fixture]
    with conn.cursor() as cur:
        cur.execute(DDL)
        if users:
            cur.execute(USERS_SQL, {"users": users})
        if orders:
            cur.execute(ORDERS_SQL, {"users": users, "orders": orders})
        cur.execute("ANALYZE seed_snapshots.users, seed_snapshots.orders")
    conn.commit()
