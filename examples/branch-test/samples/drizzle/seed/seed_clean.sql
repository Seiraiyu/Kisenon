TRUNCATE "users" RESTART IDENTITY;
INSERT INTO "users" ("email", "name") VALUES
  ('alice@example.com', 'Alice'),
  ('bob@example.com', 'Bob'),
  ('carol@example.com', 'Carol'),
  ('dan@example.com', 'Dan'),
  ('eve@example.com', 'Eve');
