// Live mode: the webhook endpoint. `stripe listen --forward-to localhost:4242/webhook`.
import express from "express";
import Stripe from "stripe";
import { loadEnv, pool, requireEnv } from "./db";
import { ingest } from "./handler";

loadEnv();
const secret = requireEnv("STRIPE_WEBHOOK_SECRET");
const db = pool(requireEnv("KISENON_URL"));
const app = express();

app.post("/webhook", express.raw({ type: "application/json" }), async (req, res) => {
  let event: Stripe.Event;
  try {
    event = Stripe.webhooks.constructEvent(req.body, req.header("stripe-signature") ?? "", secret);
  } catch (e) {
    res.status(400).send(`Webhook signature check failed: ${(e as Error).message}`);
    return;
  }
  const client = await db.connect();
  try {
    const fresh = await ingest(client, event);
    process.stderr.write(`[${fresh ? "stored" : "duplicate"}: ${event.id} | ${event.type}]\n`);
    res.json({ received: true, duplicate: !fresh });
  } finally {
    client.release();
  }
});

const port = Number(process.env.PORT ?? 4242);
app.listen(port, () => process.stderr.write(`[listening: http://localhost:${port}/webhook]\n`));
