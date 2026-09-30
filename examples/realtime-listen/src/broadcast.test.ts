import { expect, it } from "vitest";
import { broadcast, parseChange } from "./broadcast.js";

it("parses a trigger payload", () => {
  const c = parseChange('{"op":"INSERT","table":"items","row":{"id":1,"name":"a"}}');
  expect(c).toEqual({ op: "INSERT", table: "items", row: { id: 1, name: "a" } });
});

it("rejects junk payloads", () => {
  expect(parseChange(undefined)).toBeNull();
  expect(parseChange("not json")).toBeNull();
  expect(parseChange('{"hello":1}')).toBeNull();
});

it("sends only to open sockets and counts them", () => {
  const sent: string[] = [];
  const open = { readyState: 1, send: (d: string) => sent.push(d) };
  const closing = { readyState: 2, send: () => { throw new Error("closed"); } };
  expect(broadcast([open, closing, open], "x")).toBe(2);
  expect(sent).toEqual(["x", "x"]);
});
