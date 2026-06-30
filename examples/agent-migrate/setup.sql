-- agent-sandbox demo dataset.
-- Run once against $KISENON_URL on `main`:
--   psql "$KISENON_URL" -f setup.sql
--
-- Idempotent. Designed so each of the three README demos has real numbers.

DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders       CASCADE;
DROP TABLE IF EXISTS products     CASCADE;
DROP TABLE IF EXISTS users        CASCADE;

CREATE TABLE users (
  id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email       VARCHAR(50)  NOT NULL,
  full_name   VARCHAR(120) NOT NULL,
  signup_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
  last_login  TIMESTAMPTZ
);

CREATE TABLE products (
  id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sku         VARCHAR(40)  NOT NULL UNIQUE,
  name        VARCHAR(120) NOT NULL,
  price_cents INTEGER      NOT NULL CHECK (price_cents >= 0)
);

CREATE TABLE orders (
  id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  customer_id  INTEGER     NOT NULL REFERENCES users(id),
  total_cents  INTEGER     NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Note: NO INDEX on orders.customer_id. Demo 2 makes the agent add it.

CREATE TABLE order_items (
  id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id    INTEGER NOT NULL REFERENCES orders(id),
  product_id  INTEGER NOT NULL REFERENCES products(id),
  quantity    INTEGER NOT NULL DEFAULT 1
);

-- 10,000 users with last_login uniformly across the last 4 years -> ~50% over 2y.
INSERT INTO users (email, full_name, last_login)
SELECT
  'user' || i || '@example.com',
  'User ' || i,
  now() - (random() * INTERVAL '4 years')
FROM generate_series(1, 10000) i;

-- 1,000 products.
INSERT INTO products (sku, name, price_cents)
SELECT
  'SKU-' || lpad(i::text, 6, '0'),
  'Product ' || i,
  99 + (i * 13) % 9000
FROM generate_series(1, 1000) i;

-- 50,000 orders distributed across users + the last 2 years.
INSERT INTO orders (customer_id, total_cents, created_at)
SELECT
  1 + (random() * 9999)::int,
  100 + (random() * 19900)::int,
  now() - (random() * INTERVAL '2 years')
FROM generate_series(1, 50000);

-- ~200,000 order_items (avg 4 items per order).
INSERT INTO order_items (order_id, product_id, quantity)
SELECT
  1 + (random() * 49999)::int,
  1 + (random() * 999)::int,
  1 + (random() * 4)::int
FROM generate_series(1, 200000);

ANALYZE;
