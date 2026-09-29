-- Smoke test run on the PR's fork. Replace with your real test suite.
BEGIN;
INSERT INTO gh_preview.todos (title) VALUES ('ci smoke test');
DO $$
BEGIN
  IF (SELECT count(*) FROM gh_preview.todos WHERE title = 'ci smoke test') <> 1 THEN
    RAISE EXCEPTION 'insert into gh_preview.todos failed';
  END IF;
END $$;
ROLLBACK;
