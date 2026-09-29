# stripe-webhook-replay

A Stripe webhook handler that stores every event once (an append-only
`stripe_events` log, unique on the event id) and projects it into `users`
and `subscriptions`. The trick: **before you deploy a handler change,
replay your entire real event history through the new code on a Kisenon
fork of production, and diff the result against what production has now.**

Runs fully offline from a committed fixture log. Live mode uses the Stripe
CLI and a test-mode key.

## Why this needs Kisenon

"What would this handler change do to our existing customers?" is
normally answered by reading code and hoping. Replaying months of events
needs a database with production's event log that you're allowed to
truncate and rebuild. `npm run replay` forks `main` (~3 s, including
waiting for the fork's endpoint), truncates
the projections **on the fork**, rebuilds them from the log with the code
on disk, diffs, and deletes the fork. Production isn't touched.

## What you need

- A Kisenon account, `keon` CLI installed and logged in
  (`curl -fsSL https://kisenon.com/install.sh | bash`, then `keon login`).
- `psql`, Node.js 20.12+.
- Live mode only: the [Stripe CLI](https://docs.stripe.com/stripe-cli) and a Stripe account in test mode.

## Bring your own keys

| Key | Where to get it | Required? | Without it |
|---|---|---|---|
| `KISENON_PROJECT_ID` | `keon projects list -o json` | required for `replay` | exit 2 |
| `KISENON_URL` | `keon connection-string main --project <id>` | required | exit 2 |
| `STRIPE_SECRET_KEY` | Stripe dashboard → Developers → API keys (**test mode**) | live mode only (used by the Stripe CLI) | use offline mode (`npm run seed`) |
| `STRIPE_WEBHOOK_SECRET` | printed by `stripe listen --print-secret` | live mode only (`npm run server`) | `npm run server` exits 2; offline mode unaffected |

## Setup

```bash
cd examples/stripe-webhook-replay
npm install
cp .env.example .env        # fill in KISENON_PROJECT_ID and KISENON_URL
set -a; . ./.env; set +a
psql "$KISENON_URL" -f schema.sql
```

## Offline demo (no Stripe account)

```bash
npm run seed
```

```text
[seeded: 56 new | duplicates=1]
{"deliveries":57,"stored":56,"duplicates":1}
```

Running it again stores nothing — every delivery is a duplicate:

```text
[seeded: 0 new | duplicates=57]
{"deliveries":57,"stored":0,"duplicates":57}
```

(`pg` also prints a `SECURITY WARNING` about `sslmode` aliases; it is
harmless and omitted from the outputs here.)

`fixtures/events.jsonl` is 57 synthetic deliveries for 20 customers: sign-ups,
trials, payment failures (`past_due`), recoveries, cancellations, one Stripe
retry (duplicate id — stored once) and one out-of-order pair (the older
event is ignored). Regenerate with `npm run make-fixture`.

Replay with unchanged code — nothing differs:

```bash
npm run replay; echo "exit=$?"
```

```text
[branch forked: stripe-webhook-replay-fedd00fc | 2949ms]
[replayed: 56 events]
Replayed 56 events on stripe-webhook-replay-fedd00fc with the handler on disk.
users: identical
subscriptions: identical
{"branch":{"name":"stripe-webhook-replay-fedd00fc","id":"0e9c9965-e4af-4406-a628-8de4f964ce19","kept":false},"events":56,"changed":0,"diffs":{"users":[],"subscriptions":[]}}
[branch deleted: 0e9c9965-e4af-4406-a628-8de4f964ce19]
exit=0
```

Now change the business rule — "keep people on the paid plan while their
card is failing" — by adding `past_due` to `PAID_STATUSES` in
`src/handler.ts`:

```bash
sed -i.bak 's/new Set(\["active", "trialing"\])/new Set(["active", "trialing", "past_due"])/' src/handler.ts
npm run replay; echo "exit=$?"
```

```text
[branch forked: stripe-webhook-replay-b6e7bf12 | 3306ms]
[replayed: 56 events]
Replayed 56 events on stripe-webhook-replay-b6e7bf12 with the handler on disk.
users: 3 rows differ
  cus_fixture_003: main={"stripe_id":"cus_fixture_003","email":"customer003@example.com","type":"free-trial"} fork={"stripe_id":"cus_fixture_003","email":"customer003@example.com","type":"paid"}
  cus_fixture_009: main={"stripe_id":"cus_fixture_009","email":"customer009@example.com","type":"free-trial"} fork={"stripe_id":"cus_fixture_009","email":"customer009@example.com","type":"paid"}
  cus_fixture_015: main={"stripe_id":"cus_fixture_015","email":"customer015@example.com","type":"free-trial"} fork={"stripe_id":"cus_fixture_015","email":"customer015@example.com","type":"paid"}
subscriptions: identical
{"branch":{"name":"stripe-webhook-replay-b6e7bf12","id":"12696be2-a447-44f2-8d75-dd93c841b2ec","kept":false},"events":56,"changed":3,"diffs":{"users":[ …the same three rows… ],"subscriptions":[]}}
[branch deleted: 12696be2-a447-44f2-8d75-dd93c841b2ec]
exit=1
```

Exactly the three customers currently `past_due` would be upgraded. Put it
back with `mv src/handler.ts.bak src/handler.ts`.

## Live mode (Stripe test mode)

> Live mode: untested — no Stripe test key during verification.

```bash
# 1. Get the signing secret and put it in .env as STRIPE_WEBHOOK_SECRET
stripe listen --api-key "$STRIPE_SECRET_KEY" --print-secret
set -a; . ./.env; set +a

# 2. Terminal A: forward Stripe events to the server
stripe listen --api-key "$STRIPE_SECRET_KEY" --forward-to localhost:4242/webhook

# 3. Terminal B: the webhook server
npm run server

# 4. Terminal C: create test-mode activity, then replay
stripe trigger customer.subscription.created --api-key "$STRIPE_SECRET_KEY"
npm run replay
```

The server logs `[stored: evt_… | customer.subscription.created]` per event
(and `[duplicate: …]` when Stripe retries). Events from `seed` and from live
mode share the same log.

## Output and exit codes

`replay` prints a per-table summary and one JSON line (`--pretty` suppresses
it); `--keep` keeps the fork; `--project` overrides `KISENON_PROJECT_ID`.

| Code | Meaning |
|---|---|
| `0` | Projections identical — the change doesn't alter existing state. |
| `1` | Projections differ (details above / in the JSON). Use this as a CI gate. |
| `2` | Setup failure: missing env, `keon` error, database error. |

## Limitations

- Handles `customer.created/updated` and `customer.subscription.created/updated/deleted`; other types are stored and ignored.
- Replay order is Stripe's `created` timestamp, then event id. Events in the same second are ordered by id.
- The replay rebuilds projections from scratch; side effects (emails, API calls) aren't part of the handler and aren't replayed.
- Live mode: untested — no Stripe test key during verification.

## Credits

The `users` model and the paid/free-trial logic are adapted from
[benawad/graphql-typescript-stripe-example](https://github.com/benawad/graphql-typescript-stripe-example)
(MIT, © 2018 Ben Awad). See [`NOTICE`](NOTICE).
