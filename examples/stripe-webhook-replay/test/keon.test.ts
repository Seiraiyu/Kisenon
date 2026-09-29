import { execFileSync } from "node:child_process";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { branchUrl, createFork, deleteBranch } from "../src/keon";

vi.mock("node:child_process", () => ({ execFileSync: vi.fn() }));
const run = vi.mocked(execFileSync);

beforeEach(() => {
  run.mockReset(); // block body: a returned function would run as a teardown hook
});

describe("keon wrapper", () => {
  it("createFork resolves main, then creates with --wait", () => {
    run
      .mockReturnValueOnce(JSON.stringify({ branches: [{ id: "m1", name: "main" }] }) as never)
      .mockReturnValueOnce(JSON.stringify({ branch: { id: "b1", name: "swr-1" } }) as never);
    expect(createFork("p", "swr-1")).toEqual({ id: "b1", name: "swr-1" });
    expect(run.mock.calls[1][1]).toEqual([
      "branches", "create", "--project", "p", "--name", "swr-1",
      "--parent-id", "m1", "--wait", "-o", "json",
    ]);
  });

  it("createFork fails clearly without a main branch", () => {
    run.mockReturnValueOnce(JSON.stringify({ branches: [] }) as never);
    expect(() => createFork("p", "x")).toThrow(/no branch named 'main'/);
  });

  it("branchUrl reads connection_string", () => {
    run.mockReturnValueOnce(JSON.stringify({ connection_string: "postgresql://f" }) as never);
    expect(branchUrl("p", "swr-1")).toBe("postgresql://f");
    expect(run.mock.calls[0][1]).toEqual(["connection-string", "swr-1", "--project", "p", "-o", "json"]);
  });

  it("deleteBranch cascades", () => {
    run.mockReturnValueOnce("" as never);
    deleteBranch("b1");
    expect(run.mock.calls[0][1]).toEqual(["branches", "delete", "--cascade", "b1"]);
  });

  it("maps a missing binary to an install hint", () => {
    run.mockImplementation(() => {
      throw Object.assign(new Error("spawn keon ENOENT"), { code: "ENOENT" });
    });
    expect(() => deleteBranch("b1")).toThrow(/not on PATH/);
  });

  it("surfaces keon's stderr on failure", () => {
    run.mockImplementation(() => {
      throw Object.assign(new Error("Command failed"), { status: 1, stderr: "cp 409 conflict" });
    });
    expect(() => deleteBranch("b1")).toThrow(/cp 409 conflict/);
  });
});
