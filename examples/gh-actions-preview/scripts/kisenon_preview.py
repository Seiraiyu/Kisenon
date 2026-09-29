#!/usr/bin/env python3
"""Kisenon preview branches for pull requests.

Called by .github/workflows/kisenon-preview.yml. Stdlib only, so the workflow
needs no `pip install`. Runs locally too:

  KISENON_PROJECT_ID=<id> python3 scripts/kisenon_preview.py up --pr 7

  up       fork main as pr-<n>, or reset pr-<n> to main if it already exists;
           export DATABASE_URL (masked) to $GITHUB_ENV, or print it locally
  comment  write the sticky PR comment (results, schema diff, connect hint)
  down     delete pr-<n>; no-op if it is already gone

Exit codes: 0 ok, 1 a keon call failed, 2 setup error (missing env / keon).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit

MAX_DIFF_CHARS = 50_000  # GitHub caps a comment at 65,536 chars


class KeonError(RuntimeError):
    """`keon` ran but exited non-zero."""


class KeonNotFound(KeonError):
    """`keon` binary isn't on PATH."""


def event(msg: str) -> None:
    print(f"[{msg}]", file=sys.stderr, flush=True)


def keon(*args: str) -> str:
    try:
        proc = subprocess.run(["keon", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise KeonNotFound(
            "`keon` is not on PATH. Install: curl -fsSL https://kisenon.com/install.sh | sh"
        ) from e
    if proc.returncode != 0:
        raise KeonError(
            f"`keon {' '.join(args)}` failed ({proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    return proc.stdout


def branch_ids(project: str) -> dict[str, str]:
    data = json.loads(keon("branches", "list", "--project", project, "-o", "json"))
    return {b["name"]: str(b["id"]) for b in data.get("branches", [])}


def connection_url(project: str, branch: str) -> str:
    data = json.loads(keon("connection-string", branch, "--project", project, "-o", "json"))
    url = data.get("connection_string")
    if not url:
        raise KeonError(f"`keon connection-string {branch}` returned no connection_string")
    return url


def redact(url: str) -> str:
    parts = urlsplit(url)
    if not parts.password:
        return url
    netloc = parts.netloc.replace(f":{parts.password}@", ":****@", 1)
    return parts._replace(netloc=netloc).geturl()


def mask(url: str) -> None:
    """Tell GitHub Actions to scrub the password and URL from every log line."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    password = urlsplit(url).password
    if password:
        print(f"::add-mask::{password}", flush=True)
    print(f"::add-mask::{url}", flush=True)


def ensure_branch(project: str, name: str) -> tuple[str, str]:
    """Return (branch_id, 'created' | 'reset')."""
    existing = branch_ids(project).get(name)
    if existing:
        keon("branches", "reset", existing, "-o", "json")
        return existing, "reset"
    out = json.loads(keon(
        "branches", "create", "--project", project, "--name", name, "--wait", "-o", "json",
    ))
    return str(out["branch"]["id"]), "created"


def wake(url: str) -> None:
    """schema-diff needs a running endpoint; a connection wakes a suspended one."""
    try:
        subprocess.run(["psql", url, "-qAtc", "select 1"],
                       capture_output=True, check=False, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def schema_diff(project: str, name: str) -> str:
    try:
        ids = branch_ids(project)
        if "main" not in ids or name not in ids:
            return f"schema diff unavailable: branch main or {name} not found"
        main_url = connection_url(project, "main")
        mask(main_url)
        wake(main_url)
        raw = keon("branches", "schema-diff", ids["main"], ids[name], "-o", "json")
        return json.dumps(json.loads(raw), indent=2)
    except (KeonError, ValueError) as e:
        return f"schema diff unavailable: {e}"


def render_comment(*, name: str, migrations: str, tests: str, diff: str, url: str) -> str:
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n... (truncated)"
    return f"""## Kisenon preview branch `{name}`

Forked from `main` on every push to this PR.

| Step | Result |
|---|---|
| Migrations | {migrations} |
| Tests | {tests} |

<details><summary>Schema diff vs main</summary>

```json
{diff}
```

</details>

Connect (password not shown):

```
{redact(url)}
keon connection-string {name} --project $KISENON_PROJECT_ID
```

The branch is deleted when this PR is closed.
"""


def cmd_up(args: argparse.Namespace, project: str) -> int:
    name = f"pr-{args.pr}"
    branch_id, action = ensure_branch(project, name)
    event(f"branch {action}: {name} | id={branch_id}")
    url = connection_url(project, name)
    mask(url)
    env_file = os.environ.get("GITHUB_ENV")
    if env_file:
        with open(env_file, "a") as f:
            f.write(f"DATABASE_URL={url}\n")
    else:
        print(url)
    return 0


def cmd_comment(args: argparse.Namespace, project: str) -> int:
    name = f"pr-{args.pr}"
    url = connection_url(project, name)
    mask(url)
    body = render_comment(
        name=name, migrations=args.migrations, tests=args.tests,
        diff=schema_diff(project, name), url=url,
    )
    with open(args.out, "w") as f:
        f.write(body)
    event(f"comment written: {args.out}")
    return 0


def cmd_down(args: argparse.Namespace, project: str) -> int:
    name = f"pr-{args.pr}"
    branch_id = branch_ids(project).get(name)
    if not branch_id:
        event(f"nothing to delete: {name}")
        return 0
    keon("branches", "delete", "--cascade", branch_id)
    event(f"branch deleted: {name} | id={branch_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kisenon_preview")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd in ("up", "comment", "down"):
        p = sub.add_parser(cmd)
        p.add_argument("--pr", type=int, required=True)
        if cmd == "comment":
            p.add_argument("--migrations", default="skipped")
            p.add_argument("--tests", default="skipped")
            p.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    project = os.environ.get("KISENON_PROJECT_ID")
    if not project:
        print("KISENON_PROJECT_ID is not set (repo variable in CI, .env locally)",
              file=sys.stderr)
        return 2
    handlers = {"up": cmd_up, "comment": cmd_comment, "down": cmd_down}
    try:
        return handlers[args.cmd](args, project)
    except KeonNotFound as e:
        print(str(e), file=sys.stderr)
        return 2
    except KeonError as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
