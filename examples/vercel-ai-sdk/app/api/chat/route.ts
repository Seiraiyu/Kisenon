import { anthropic } from "@ai-sdk/anthropic";
import {
  convertToModelMessages,
  createUIMessageStreamResponse,
  isStepCount,
  streamText,
  tool,
  toUIMessageStream,
  type UIMessage,
} from "ai";
import { z } from "zod";
import { runReadOnly } from "../../../lib/readonly";

export const maxDuration = 60;

const MODEL = "claude-sonnet-5";

const INSTRUCTIONS = `You answer questions about a small shop database (PostgreSQL 17).
Tables: customers(id, name, country, signed_up_at), products(id, name, category, price_cents),
orders(id, customer_id, product_id, quantity, created_at).
Use the query tool to run one read-only SELECT at a time. Prefer aggregates and LIMIT.
Answer with the numbers you got back, and show the SQL you used.`;

export async function POST(req: Request) {
  if (!process.env.ANTHROPIC_API_KEY) {
    return Response.json({ error: "ANTHROPIC_API_KEY is not set" }, { status: 500 });
  }
  const { messages }: { messages: UIMessage[] } = await req.json();
  const result = streamText({
    model: anthropic(MODEL),
    instructions: INSTRUCTIONS,
    messages: await convertToModelMessages(messages),
    stopWhen: isStepCount(8),
    tools: {
      query: tool({
        description: "Run one read-only SQL SELECT against the shop database. Returns up to 100 rows.",
        inputSchema: z.object({ sql: z.string().describe("A single PostgreSQL SELECT statement") }),
        execute: async ({ sql }) => runReadOnly(sql),
      }),
    },
  });
  return createUIMessageStreamResponse({ stream: toUIMessageStream({ stream: result.stream }) });
}
