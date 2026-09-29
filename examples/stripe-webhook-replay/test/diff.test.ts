import { describe, expect, it } from "vitest";
import { diffRows } from "../src/diff";

describe("diffRows", () => {
  it("reports changed, missing and extra rows by key, sorted", () => {
    const main = [{ id: "a", v: 1 }, { id: "b", v: 2 }, { id: "c", v: 3 }];
    const fork = [{ id: "a", v: 1 }, { id: "b", v: 20 }, { id: "d", v: 4 }];
    expect(diffRows(main, fork, "id")).toEqual([
      { key: "b", main: { id: "b", v: 2 }, fork: { id: "b", v: 20 } },
      { key: "c", main: { id: "c", v: 3 }, fork: null },
      { key: "d", main: null, fork: { id: "d", v: 4 } },
    ]);
  });

  it("treats equal Dates as equal", () => {
    const d = () => [{ id: "x", at: new Date("2026-01-01T00:00:00Z") }];
    expect(diffRows(d(), d(), "id")).toEqual([]);
  });
});
