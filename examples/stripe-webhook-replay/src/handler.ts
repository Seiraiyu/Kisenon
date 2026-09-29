import type Stripe from "stripe";

// Plan logic adapted from benawad/graphql-typescript-stripe-example (MIT,
// (c) 2018 Ben Awad; see NOTICE): a user is "paid" or "free-trial".
/** Subscription statuses that grant the paid plan. The README demo edits this line. */
export const PAID_STATUSES = new Set(["active", "trialing"]);

export interface Queryable {
  query(text: string, values?: unknown[]): Promise<{ rowCount: number | null }>;
}

export interface SubscriptionRow {
  id: string;
  customer: string;
  status: string;
  priceId: string | null;
  currentPeriodEnd: number | null;
  cancelAtPeriodEnd: boolean;
  lastEventCreated: number;
}

export type Projection =
  | { kind: "customer"; stripeId: string; email: string | null }
  | { kind: "subscription"; row: SubscriptionRow; userType: "paid" | "free-trial" }
  | { kind: "ignored" };

export function project(event: Stripe.Event): Projection {
  switch (event.type) {
    case "customer.created":
    case "customer.updated": {
      const c = event.data.object as Stripe.Customer;
      return { kind: "customer", stripeId: c.id, email: c.email ?? null };
    }
    case "customer.subscription.created":
    case "customer.subscription.updated":
    case "customer.subscription.deleted": {
      const s = event.data.object as Stripe.Subscription;
      const item = s.items.data[0];
      return {
        kind: "subscription",
        userType: PAID_STATUSES.has(s.status) ? "paid" : "free-trial",
        row: {
          id: s.id,
          customer: typeof s.customer === "string" ? s.customer : s.customer.id,
          status: s.status,
          priceId: item?.price.id ?? null,
          currentPeriodEnd: item?.current_period_end ?? null,
          cancelAtPeriodEnd: s.cancel_at_period_end,
          lastEventCreated: event.created,
        },
      };
    }
    default:
      return { kind: "ignored" };
  }
}

/** Apply one event to the projections. Safe to replay: older events never overwrite newer. */
export async function applyEvent(db: Queryable, event: Stripe.Event): Promise<void> {
  const p = project(event);
  if (p.kind === "customer") {
    await db.query(
      `INSERT INTO users (stripe_id, email) VALUES ($1, $2)
       ON CONFLICT (stripe_id) DO UPDATE SET email = EXCLUDED.email`,
      [p.stripeId, p.email],
    );
  } else if (p.kind === "subscription") {
    const r = p.row;
    const res = await db.query(
      `INSERT INTO subscriptions
         (id, customer, status, price_id, current_period_end, cancel_at_period_end, last_event_created)
       VALUES ($1, $2, $3, $4, to_timestamp($5), $6, $7)
       ON CONFLICT (id) DO UPDATE SET
         customer = EXCLUDED.customer, status = EXCLUDED.status, price_id = EXCLUDED.price_id,
         current_period_end = EXCLUDED.current_period_end,
         cancel_at_period_end = EXCLUDED.cancel_at_period_end,
         last_event_created = EXCLUDED.last_event_created
       WHERE subscriptions.last_event_created <= EXCLUDED.last_event_created`,
      [r.id, r.customer, r.status, r.priceId, r.currentPeriodEnd, r.cancelAtPeriodEnd,
        r.lastEventCreated],
    );
    if (res.rowCount === 1) {
      await db.query(
        `INSERT INTO users (stripe_id, type) VALUES ($1, $2)
         ON CONFLICT (stripe_id) DO UPDATE SET type = EXCLUDED.type`,
        [r.customer, p.userType],
      );
    }
  }
}

/** Store the event once (idempotent on its id) and project it in the same transaction.
 *  Returns false for a duplicate delivery. */
export async function ingest(db: Queryable, event: Stripe.Event): Promise<boolean> {
  await db.query("BEGIN");
  try {
    const res = await db.query(
      `INSERT INTO stripe_events (id, type, created, payload) VALUES ($1, $2, $3, $4)
       ON CONFLICT (id) DO NOTHING`,
      [event.id, event.type, event.created, JSON.stringify(event)],
    );
    const fresh = res.rowCount === 1;
    if (fresh) await applyEvent(db, event);
    await db.query("COMMIT");
    return fresh;
  } catch (e) {
    await db.query("ROLLBACK");
    throw e;
  }
}
