ALTER TABLE gh_preview.todos ADD COLUMN IF NOT EXISTS due_date date;
CREATE INDEX IF NOT EXISTS todos_open_due_date_idx
  ON gh_preview.todos (due_date) WHERE NOT done;
