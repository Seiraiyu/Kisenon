-- realtime-listen: a table whose every change is published on channel `realtime_listen`.
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f setup.sql
CREATE SCHEMA IF NOT EXISTS realtime_listen;

CREATE TABLE IF NOT EXISTS realtime_listen.items (
  id         int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name       text NOT NULL,
  qty        int  NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- NOTIFY payloads are capped at 8000 bytes; for wide rows send the id and let clients fetch.
CREATE OR REPLACE FUNCTION realtime_listen.notify_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_notify('realtime_listen', json_build_object(
    'op',    TG_OP,
    'table', TG_TABLE_NAME,
    'row',   CASE WHEN TG_OP = 'DELETE' THEN row_to_json(OLD) ELSE row_to_json(NEW) END
  )::text);
  RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS items_notify ON realtime_listen.items;
CREATE TRIGGER items_notify
  AFTER INSERT OR UPDATE OR DELETE ON realtime_listen.items
  FOR EACH ROW EXECUTE FUNCTION realtime_listen.notify_change();
