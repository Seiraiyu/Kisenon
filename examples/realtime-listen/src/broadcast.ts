export type Change = {
  op: "INSERT" | "UPDATE" | "DELETE";
  table: string;
  row: Record<string, unknown>;
};

export function parseChange(payload: string | undefined): Change | null {
  if (!payload) return null;
  try {
    const c = JSON.parse(payload);
    return c && typeof c.op === "string" && c.row && typeof c.row === "object" ? (c as Change) : null;
  } catch {
    return null;
  }
}

const OPEN = 1; // WebSocket.OPEN

export function broadcast(
  clients: Iterable<{ readyState: number; send(data: string): void }>,
  message: string,
): number {
  let n = 0;
  for (const c of clients) {
    if (c.readyState === OPEN) {
      c.send(message);
      n++;
    }
  }
  return n;
}
