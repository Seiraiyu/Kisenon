TRUNCATE "users" RESTART IDENTITY;
INSERT INTO "users" ("email", "name") VALUES
  ('alice@example.com', 'Alice One'),
  ('alice@example.com', 'Alice Two'),
  ('carol@example.com', NULL),
  ('dan@example.com', 'Dan'),
  ('eve@example.com', 'Eve');
