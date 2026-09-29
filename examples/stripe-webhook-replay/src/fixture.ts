// Synthetic Stripe events for offline mode. Deterministic: `npm run make-fixture`
// rewrites fixtures/events.jsonl byte-for-byte.
type Obj = Record<string, unknown>;

const T0 = 1767225600; // 2026-01-01T00:00:00Z
const DAY = 86400;
const API_VERSION = "2026-08-26.dahlia";
const pad = (n: number) => String(n).padStart(3, "0");

function customer(k: number, created: number): Obj {
  return {
    id: `cus_fixture_${pad(k)}`,
    object: "customer",
    created,
    email: `customer${pad(k)}@example.com`,
    name: `Customer ${k}`,
    livemode: false,
    metadata: {},
  };
}

function subscription(k: number, status: string, cancelAtPeriodEnd = false): Obj {
  const start = T0 + k * DAY;
  const sub = `sub_fixture_${pad(k)}`;
  return {
    id: sub,
    object: "subscription",
    customer: `cus_fixture_${pad(k)}`,
    status,
    cancel_at_period_end: cancelAtPeriodEnd,
    created: start,
    currency: "usd",
    livemode: false,
    metadata: {},
    items: {
      object: "list",
      has_more: false,
      url: `/v1/subscription_items?subscription=${sub}`,
      data: [
        {
          id: `si_fixture_${pad(k)}`,
          object: "subscription_item",
          created: start,
          quantity: 1,
          subscription: sub,
          current_period_start: start,
          current_period_end: start + 30 * DAY,
          metadata: {},
          price: {
            id: "price_fixture_pro",
            object: "price",
            active: true,
            currency: "usd",
            unit_amount: 2000,
            type: "recurring",
            recurring: { interval: "month", interval_count: 1 },
            product: "prod_fixture_pro",
            livemode: false,
          },
        },
      ],
    },
  };
}

export function buildEvents(): Obj[] {
  let seq = 0;
  const event = (type: string, created: number, object: Obj, previous?: Obj): Obj => {
    seq += 1;
    return {
      id: `evt_fixture_${String(seq).padStart(4, "0")}`,
      object: "event",
      api_version: API_VERSION,
      created,
      data: previous ? { object, previous_attributes: previous } : { object },
      livemode: false,
      pending_webhooks: 0,
      request: { id: null, idempotency_key: null },
      type,
    };
  };

  const events: Obj[] = [];
  for (let k = 1; k <= 20; k++) {
    const t = T0 + k * DAY;
    const first = k % 5 === 0 ? "trialing" : "active";
    events.push(event("customer.created", t, customer(k, t)));
    events.push(event("customer.subscription.created", t + 60, subscription(k, first)));
    if (k % 3 === 0) {
      events.push(event("customer.subscription.updated", t + 10 * DAY,
        subscription(k, "past_due"), { status: first }));
    }
    if (k % 6 === 0) {
      events.push(event("customer.subscription.updated", t + 12 * DAY,
        subscription(k, "active"), { status: "past_due" }));
    }
    if (k % 4 === 0) {
      events.push(event("customer.subscription.deleted", t + 20 * DAY, subscription(k, "canceled")));
    }
  }
  // Stripe retries: the same event (same id) delivered twice. Must be stored once.
  events.push(events[1]);
  // Out-of-order delivery: the newer update arrives before the older one.
  const t2 = T0 + 2 * DAY;
  events.push(event("customer.subscription.updated", t2 + 5 * DAY,
    subscription(2, "active", true), { cancel_at_period_end: false }));
  events.push(event("customer.subscription.updated", t2 + 3 * DAY,
    subscription(2, "active", false), { cancel_at_period_end: true }));
  return events;
}
