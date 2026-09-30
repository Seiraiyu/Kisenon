-- vercel-ai-sdk demo dataset (deterministic). Run as the owner role:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f setup.sql
-- Re-run readonly.sql afterwards: GRANT ... ON ALL TABLES only covers tables that exist.
DROP SCHEMA IF EXISTS vercel_ai_sdk CASCADE;
CREATE SCHEMA vercel_ai_sdk;
SET search_path = vercel_ai_sdk;

CREATE TABLE customers (
  id           int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name         text NOT NULL,
  country      text NOT NULL,
  signed_up_at timestamptz NOT NULL
);
CREATE TABLE products (
  id          int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        text NOT NULL,
  category    text NOT NULL,
  price_cents int  NOT NULL CHECK (price_cents >= 0)
);
CREATE TABLE orders (
  id          int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  customer_id int NOT NULL REFERENCES customers(id),
  product_id  int NOT NULL REFERENCES products(id),
  quantity    int NOT NULL,
  created_at  timestamptz NOT NULL
);

INSERT INTO customers (name, country, signed_up_at)
SELECT 'Customer ' || i,
       (ARRAY['US','DE','PT','JP','BR','IN'])[1 + i % 6],
       now() - (i % 730) * interval '1 day'
FROM generate_series(1, 1000) i;

INSERT INTO products (name, category, price_cents)
SELECT 'Product ' || i,
       (ARRAY['books','games','garden','kitchen','toys'])[1 + i % 5],
       199 + (i * 37) % 9800
FROM generate_series(1, 200) i;

INSERT INTO orders (customer_id, product_id, quantity, created_at)
SELECT 1 + (i * 7919) % 1000,
       1 + (i * 104729) % 200,
       1 + i % 4,
       now() - (i % 365) * interval '1 day' - (i % 24) * interval '1 hour'
FROM generate_series(1, 5000) i;

ANALYZE customers, products, orders;
