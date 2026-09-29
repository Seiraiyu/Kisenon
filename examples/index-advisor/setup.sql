-- index-advisor dataset. Run once against $KISENON_URL (main):
--   psql "$KISENON_URL" -f setup.sql
-- Deterministic; only primary keys are indexed, so the workload has something to fix.
-- pg_stat_statements is created separately (see README Setup) so a missing
-- extension doesn't abort the data load.
CREATE SCHEMA IF NOT EXISTS index_advisor;
SET search_path TO index_advisor;

DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
  id          integer     PRIMARY KEY,
  email       text        NOT NULL,
  region      text        NOT NULL,
  created_at  timestamptz NOT NULL
);

CREATE TABLE orders (
  id           bigint      PRIMARY KEY,
  customer_id  integer     NOT NULL,
  status       text        NOT NULL,
  total_cents  integer     NOT NULL,
  created_at   timestamptz NOT NULL
);

-- Mixed-case emails: the workload looks them up with lower(email).
INSERT INTO customers (id, email, region, created_at)
SELECT i,
       'Customer' || i || '@Example.com',
       (ARRAY['na', 'eu', 'apac'])[1 + i % 3],
       TIMESTAMPTZ '2026-06-30 00:00:00+00' - (i % 1000) * INTERVAL '1 day'
FROM generate_series(1, 100000) i;

INSERT INTO orders (id, customer_id, status, total_cents, created_at)
SELECT i,
       1 + (i * 7919) % 100000,
       (ARRAY['paid', 'pending', 'refunded', 'shipped'])[1 + i % 4],
       100 + (i * 37) % 50000,
       TIMESTAMPTZ '2026-06-30 00:00:00+00' - ((i * 104729) % 31536000) * INTERVAL '1 second'
FROM generate_series(1::bigint, 1000000) i;  -- bigint: i * 104729 overflows integer

ANALYZE customers;
ANALYZE orders;
