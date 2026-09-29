import { readFileSync } from "node:fs";
import Stripe from "stripe";
import { describe, expect, it } from "vitest";
import { buildEvents } from "../src/fixture";

const lines = readFileSync(new URL("../fixtures/events.jsonl", import.meta.url), "utf8")
  .trim()
  .split("\n");
const events = lines.map((l) => JSON.parse(l));

describe("fixtures/events.jsonl", () => {
  it("is exactly what the generator produces", () => {
    expect(buildEvents().map((e) => JSON.stringify(e))).toEqual(lines);
  });

  it("has the Stripe Event envelope on every line", () => {
    for (const e of events) {
      expect(e.object).toBe("event");
      expect(e.id).toMatch(/^evt_fixture_\d{4}$/);
      expect(e.api_version).toBe("2026-08-26.dahlia");
      expect(typeof e.created).toBe("number");
      expect(e.livemode).toBe(false);
      expect(e.request).toEqual({ id: null, idempotency_key: null });
      expect(e.data.object.id).toMatch(/_fixture_/);
    }
  });

  it("contains one duplicate delivery and 56 unique events", () => {
    expect(lines).toHaveLength(57);
    expect(new Set(events.map((e) => e.id)).size).toBe(56);
  });

  it("uses only synthetic ids and example.com emails", () => {
    const text = lines.join("\n");
    expect(text).not.toMatch(/"(evt|cus|sub|si|price|prod)_(?!fixture_)/);
    for (const m of text.matchAll(/"email":"([^"]+)"/g)) expect(m[1]).toMatch(/@example\.com$/);
  });

  it("is accepted by Stripe's webhook verifier", () => {
    const payload = lines[0];
    const header = Stripe.webhooks.generateTestHeaderString({ payload, secret: "test_secret" });
    expect(Stripe.webhooks.constructEvent(payload, header, "test_secret").id).toBe(events[0].id);
  });
});
