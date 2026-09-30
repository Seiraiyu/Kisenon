-- Lock the ai_readonly role down to SELECT on the demo schema.
-- Create the role first (Kisenon manages login roles):
--   keon roles create ai_readonly --branch <main-branch-id> -o json
-- then, as the owner role:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f readonly.sql
-- `keon roles create` makes an app role: CREATEDB, member of kisenon_users, and
-- CREATE on schema public. Take all three away.
ALTER ROLE ai_readonly NOCREATEDB;
REVOKE kisenon_users FROM ai_readonly;
REVOKE CREATE ON SCHEMA public FROM ai_readonly;

GRANT USAGE ON SCHEMA vercel_ai_sdk TO ai_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA vercel_ai_sdk TO ai_readonly;

-- Role defaults: enforced by Postgres even if the app forgets its own guards.
ALTER ROLE ai_readonly SET statement_timeout = '5s';
ALTER ROLE ai_readonly SET default_transaction_read_only = on;
ALTER ROLE ai_readonly SET search_path = vercel_ai_sdk;
