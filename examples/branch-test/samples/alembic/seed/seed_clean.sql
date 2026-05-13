-- Clean seed: distinct emails, all names populated.
-- Run against your main URL (NOT the branch) before invoking branch-test;
-- the branch is forked from this state.
TRUNCATE users RESTART IDENTITY;
INSERT INTO users (email, name) VALUES
  ('alice@example.com', 'Alice'),
  ('bob@example.com', 'Bob'),
  ('carol@example.com', 'Carol'),
  ('dan@example.com', 'Dan'),
  ('eve@example.com', 'Eve');
