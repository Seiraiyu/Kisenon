-- Idempotent on purpose: CI re-runs every migration against a fresh fork of
-- main, which already has the ones merged earlier. Real projects use their
-- migration tool (Alembic, Prisma, sqitch, ...) and its own bookkeeping.
CREATE SCHEMA IF NOT EXISTS gh_preview;

CREATE TABLE IF NOT EXISTS gh_preview.todos (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title      text NOT NULL,
  done       boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
