-- stripe-webhook-replay schema. Run against $KISENON_URL (main):
--   psql "$KISENON_URL" -f schema.sql
-- Re-running wipes the event log and projections.
CREATE SCHEMA IF NOT EXISTS stripe_webhook_replay;
SET search_path TO stripe_webhook_replay;

DROP TABLE IF EXISTS stripe_events;
DROP TABLE IF EXISTS subscriptions;
DROP TABLE IF EXISTS users;

-- The source of truth: every Stripe event exactly once (id is the idempotency key).
CREATE TABLE stripe_events (
  id           text        PRIMARY KEY,
  type         text        NOT NULL,
  created      bigint      NOT NULL,          -- Stripe's unix seconds
  payload      jsonb       NOT NULL,
  received_at  timestamptz NOT NULL DEFAULT now()
);

-- Projections, rebuilt from the log. `users` shape adapted from
-- benawad/graphql-typescript-stripe-example (MIT, (c) 2018 Ben Awad) — see NOTICE.
CREATE TABLE users (
  id         serial PRIMARY KEY,
  email      text,
  stripe_id  text   NOT NULL UNIQUE,
  type       text   NOT NULL DEFAULT 'free-trial'
);

CREATE TABLE subscriptions (
  id                    text        PRIMARY KEY,
  customer              text        NOT NULL,
  status                text        NOT NULL,
  price_id              text,
  current_period_end    timestamptz,
  cancel_at_period_end  boolean     NOT NULL,
  last_event_created    bigint      NOT NULL   -- guards against out-of-order delivery
);
