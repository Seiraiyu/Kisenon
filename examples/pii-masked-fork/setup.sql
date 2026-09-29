-- pii-masked-fork dataset. Run once against $KISENON_URL (main):
--   psql "$KISENON_URL" -f setup.sql
-- Synthetic "production" customers with PII in obvious AND non-obvious places
-- (the free-text `notes` column embeds emails and phone numbers).
CREATE SCHEMA IF NOT EXISTS pii_masked_fork;
SET search_path TO pii_masked_fork;

DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
  id          integer PRIMARY KEY,
  email       text NOT NULL,
  full_name   text NOT NULL,
  phone       text,
  ssn         text,
  loyalty_id  text NOT NULL,
  notes       text,
  signup_on   date NOT NULL
);

CREATE TABLE orders (
  id           integer PRIMARY KEY,
  customer_id  integer NOT NULL REFERENCES customers(id),
  total_cents  integer NOT NULL,
  status       text    NOT NULL
);

INSERT INTO customers (id, email, full_name, phone, ssn, loyalty_id, notes, signup_on)
SELECT i,
       'person' || i || '@acme-mail.com',
       (ARRAY['Alex', 'Sam', 'Jordan', 'Taylor', 'Morgan', 'Riley'])[1 + i % 6] || ' ' ||
       (ARRAY['Rivera', 'Chen', 'Okafor', 'Novak', 'Silva', 'Kim'])[1 + (i / 6) % 6],
       '+1-555-' || lpad(((i * 37) % 1000)::text, 3, '0') || '-' || lpad((i % 10000)::text, 4, '0'),
       lpad((100 + i % 800)::text, 3, '0') || '-' || lpad((i % 100)::text, 2, '0') || '-' ||
       lpad((1000 + i)::text, 4, '0'),
       'LOY-' || lpad(i::text, 6, '0'),
       CASE i % 10
         WHEN 0 THEN 'Prefers email at person' || i || '@acme-mail.com'
         WHEN 1 THEN 'Call back on +1-555-' || lpad(((i * 37) % 1000)::text, 3, '0') || '-' ||
                     lpad((i % 10000)::text, 4, '0')
         ELSE 'Loyal customer'
       END,
       DATE '2026-06-30' - (i % 1000)
FROM generate_series(1, 5000) i;

INSERT INTO orders (id, customer_id, total_cents, status)
SELECT i, 1 + (i * 7) % 5000, 500 + (i * 37) % 20000,
       (ARRAY['paid', 'shipped', 'pending'])[1 + i % 3]
FROM generate_series(1, 20000) i;

ANALYZE customers;
ANALYZE orders;
