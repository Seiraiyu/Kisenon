-- text2sql-eval dataset. Run once against $KISENON_URL (main):
--   psql "$KISENON_URL" -f setup.sql
-- Idempotent. Deterministic: expected answers in cases.yaml depend on it.
CREATE SCHEMA IF NOT EXISTS text2sql_eval;
SET search_path TO text2sql_eval;

DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
  id          integer PRIMARY KEY,
  email       text    NOT NULL UNIQUE,
  country     text    NOT NULL,
  active      boolean NOT NULL,
  last_login  date    NOT NULL
);

CREATE TABLE orders (
  id            integer PRIMARY KEY,
  user_id       integer NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  amount_cents  integer NOT NULL,
  status        text    NOT NULL CHECK (status IN ('paid', 'pending', 'refunded')),
  created_on    date    NOT NULL
);

-- 1,000 users; every 4th inactive; 5 countries evenly.
INSERT INTO users (id, email, country, active, last_login)
SELECT i,
       'user' || i || '@example.com',
       (ARRAY['US', 'DE', 'JP', 'BR', 'IN'])[1 + i % 5],
       i % 4 <> 0,
       DATE '2026-06-30' - (i % 900)
FROM generate_series(1, 1000) i;

-- 5,000 orders, only from users 1..600 (users 601..1000 never ordered).
INSERT INTO orders (id, user_id, amount_cents, status, created_on)
SELECT i,
       1 + (i * 7) % 600,
       500 + (i * 37) % 20000,
       CASE i % 10 WHEN 0 THEN 'refunded' WHEN 1 THEN 'pending' ELSE 'paid' END,
       DATE '2026-06-30' - (i % 365)
FROM generate_series(1, 5000) i;

ANALYZE users;
ANALYZE orders;
