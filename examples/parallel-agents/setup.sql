-- parallel-agents dataset. Run once against $KISENON_URL (main):
--   psql "$KISENON_URL" -f setup.sql
-- 1,000,000 events, deterministic, NO secondary indexes: the dashboard query
-- seq-scans until an agent fixes it.
CREATE SCHEMA IF NOT EXISTS parallel_agents;
SET search_path TO parallel_agents;

DROP MATERIALIZED VIEW IF EXISTS dashboard_daily;
DROP TABLE IF EXISTS events;

CREATE TABLE events (
  id          bigint      PRIMARY KEY,
  account_id  integer     NOT NULL,
  kind        text        NOT NULL,
  created_at  timestamptz NOT NULL
);

INSERT INTO events (id, account_id, kind, created_at)
SELECT i,
       1 + (i * 7919) % 2000,
       (ARRAY['view', 'click', 'signup', 'purchase'])[1 + i % 4],
       TIMESTAMPTZ '2026-06-30 00:00:00+00' - ((i * 104729) % 31536000) * INTERVAL '1 second'
FROM generate_series(1::bigint, 1000000) i;  -- bigint: i * 104729 overflows int4

ANALYZE events;
