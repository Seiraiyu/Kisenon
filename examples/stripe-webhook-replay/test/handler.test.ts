import type Stripe from "stripe";
import { describe, expect, it } from "vitest";
import { buildEvents } from "../src/fixture";
import { applyEvent, ingest, project, type Queryable } from "../src/handler";

const events = buildEvents() as unknown as Stripe.Event[];
const byType = (t: string) => events.find((e) => e.type === t)!;

class FakeDb implements Queryable {
  calls: { text: string; values?: unknown[] }[] = [];
  constructor(private rowCount: (text: string) => number = () => 1) {}
  async query(text: string, values?: unknown[]) {
    this.calls.push({ text, values });
    return { rowCount: this.rowCount(text) };
  }
}
const verbs = (db: FakeDb) => db.calls.map((c) => c.text.trim().split(/\s+/)[0]);

describe("project", () => {
  it("maps customer.created to a customer", () => {
    expect(project(byType("customer.created"))).toEqual({
      kind: "customer", stripeId: "cus_fixture_001", email: "customer001@example.com",
    });
  });

  it("maps subscription events and derives the plan type", () => {
    expect(project(byType("customer.subscription.created"))).toMatchObject({
      kind: "subscription",
      userType: "paid",
      row: {
        id: "sub_fixture_001", customer: "cus_fixture_001", status: "active",
        priceId: "price_fixture_pro", cancelAtPeriodEnd: false,
      },
    });
  });

  it("treats past_due as free-trial (the behavior the README demo changes)", () => {
    const e = events.find((x) => (x.data.object as { status?: string }).status === "past_due")!;
    expect(project(e)).toMatchObject({ kind: "subscription", userType: "free-trial" });
  });

  it("ignores other event types", () => {
    const e = { ...byType("customer.created"), type: "invoice.paid" } as Stripe.Event;
    expect(project(e)).toEqual({ kind: "ignored" });
  });
});

describe("applyEvent", () => {
  it("updates the user's plan only when the subscription row was written", async () => {
    const fresh = new FakeDb();
    await applyEvent(fresh, byType("customer.subscription.created"));
    expect(fresh.calls).toHaveLength(2);
    expect(fresh.calls[1].values).toEqual(["cus_fixture_001", "paid"]);

    const stale = new FakeDb(() => 0); // older than what's stored: upsert WHERE fails
    await applyEvent(stale, byType("customer.subscription.created"));
    expect(stale.calls).toHaveLength(1);
  });
});

describe("ingest", () => {
  it("stores and projects a new event in one transaction", async () => {
    const db = new FakeDb();
    expect(await ingest(db, byType("customer.created"))).toBe(true);
    expect(verbs(db)).toEqual(["BEGIN", "INSERT", "INSERT", "COMMIT"]);
  });

  it("skips a duplicate delivery", async () => {
    const db = new FakeDb((t) => (t.includes("stripe_events") ? 0 : 1));
    expect(await ingest(db, byType("customer.created"))).toBe(false);
    expect(verbs(db)).toEqual(["BEGIN", "INSERT", "COMMIT"]);
  });

  it("rolls back when projecting fails", async () => {
    const db = new FakeDb();
    db.query = async (text: string) => {
      db.calls.push({ text });
      if (text.includes("INTO users")) throw new Error("boom");
      return { rowCount: 1 };
    };
    await expect(ingest(db, byType("customer.created"))).rejects.toThrow("boom");
    expect(db.calls.at(-1)!.text).toBe("ROLLBACK");
  });
});
