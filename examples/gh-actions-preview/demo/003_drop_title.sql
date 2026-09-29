-- A breaking change: db/test.sql inserts into todos(title), so tests go red.
ALTER TABLE gh_preview.todos DROP COLUMN IF EXISTS title;
