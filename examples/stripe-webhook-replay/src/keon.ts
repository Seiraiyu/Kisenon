// Minimal `keon` CLI wrapper (same JSON shapes as examples/agent-sandbox/keon.py).
import { execFileSync } from "node:child_process";

export class KeonError extends Error {}

export interface Branch {
  id: string;
  name: string;
}

function keon(args: string[]): string {
  try {
    return execFileSync("keon", args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  } catch (e) {
    const err = e as NodeJS.ErrnoException & { stderr?: string };
    if (err.code === "ENOENT") {
      throw new KeonError(
        "`keon` is not on PATH. Install: curl -fsSL https://kisenon.com/install.sh | bash",
      );
    }
    throw new KeonError(`keon ${args.join(" ")} failed: ${String(err.stderr || err.message).trim()}`);
  }
}

export function createFork(project: string, name: string): Branch {
  const { branches } = JSON.parse(
    keon(["branches", "list", "--project", project, "-o", "json"]),
  ) as { branches: Branch[] };
  const main = branches.find((b) => b.name === "main");
  if (!main) throw new KeonError(`no branch named 'main' in project ${project}`);
  const { branch } = JSON.parse(
    keon([
      "branches", "create", "--project", project, "--name", name,
      "--parent-id", main.id, "--wait", "-o", "json",
    ]),
  ) as { branch: Branch };
  return { id: String(branch.id), name: branch.name ?? name };
}

export function branchUrl(project: string, branch: string): string {
  const out = JSON.parse(
    keon(["connection-string", branch, "--project", project, "-o", "json"]),
  ) as { connection_string?: string };
  if (!out.connection_string) throw new KeonError("keon connection-string returned no URL");
  return out.connection_string;
}

export function deleteBranch(id: string): void {
  keon(["branches", "delete", "--cascade", id]);
}
