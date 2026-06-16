-- Dirty seed: TWO rows share alice@example.com (which makes the UNIQUE
-- constraint in migration 003 fail), and one row has NULL name (which
-- migration 002 backfills via COALESCE -- that one succeeds).
TRUNCATE users RESTART IDENTITY;
INSERT INTO users (email, name) VALUES
  ('alice@example.com', 'Alice One'),
  ('alice@example.com', 'Alice Two'),
  ('carol@example.com', NULL),
  ('dan@example.com', 'Dan'),
  ('eve@example.com', 'Eve');
