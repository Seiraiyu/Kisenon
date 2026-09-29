"""pii-masked-fork CLI."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import uuid

from dotenv import load_dotenv

from pii_masked_fork.keon import (
    Branch,
    KeonError,
    create_branch,
    delete_branch,
    find_branch_id,
    get_branch_url,
)
from pii_masked_fork.mask import Leak, SpecError, apply_mask, connect, load_spec, verify
from pii_masked_fork.output import event, output_error, output_json


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pii-masked-fork",
        description="Fork main, mask PII per mask.yaml, verify, print the masked branch.",
    )
    p.add_argument("--mask", default="mask.yaml", help="Masking spec.")
    p.add_argument("--sample", type=int, default=1000, help="Rows sampled per text column.")
    p.add_argument("--delete", action="store_true", help="Delete the fork after verifying.")
    p.add_argument("--project", default=None, help="Override KISENON_PROJECT_ID.")
    p.add_argument("--pretty", action="store_true", help="Suppress the JSON line.")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))

    project = args.project or os.environ.get("KISENON_PROJECT_ID")
    if not project:
        output_error("KISENON_PROJECT_ID is not set (and --project not given).",
                     {"hint": "Set it in .env — see README#setup"}, exit_code=2)
    try:
        spec = load_spec(args.mask)
    except (OSError, SpecError) as e:
        output_error(str(e), exit_code=2)

    name = f"pii-masked-fork-{uuid.uuid4().hex[:8]}"
    event("mask start", schema=spec.schema, tables=len(spec.tables))
    branch: Branch | None = None
    url = ""
    masked: dict[str, int] = {}
    leaks: list[Leak] = []
    ok = False
    fatal: str | None = None
    deleted = False
    try:
        parent = find_branch_id(project=project, name="main")
        branch = create_branch(project=project, name=name, parent_id=parent)
        event("branch forked", id=branch.id, duration_ms=branch.created_in_ms)
        url = get_branch_url(project=project, branch=branch.name)
        conn = connect(url)
        try:
            masked = apply_mask(conn, spec)
            for column, rows in masked.items():
                event("masked", column=column, rows=rows)
            leaks = verify(conn, spec.schema, args.sample)
        finally:
            conn.close()
        ok = not leaks
    except Exception as e:  # noqa: BLE001 — anything before verification passes is fatal
        # First line only: Postgres' DETAIL line can echo a row that still holds raw PII.
        fatal = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"
    finally:
        # An unverified fork may still hold raw PII: delete unless verification passed.
        if branch is not None and (not ok or args.delete):
            try:
                delete_branch(branch_id=branch.id)
                deleted = True
                event("branch deleted", id=branch.id)
            except KeonError as e:
                event("cleanup failed", id=branch.id, error=e,
                      run=f"keon branches delete --cascade {branch.id}")
    if fatal:
        output_error(fatal, exit_code=2)

    if leaks:
        print("LEAKS FOUND — masked branch deleted. Add these columns to mask.yaml:")
        for lk in leaks:
            print(f"  {lk.table}.{lk.column:<14} {lk.detector:<6} {lk.hits:>5} hits"
                  f"  e.g. {lk.example}")
    else:
        print(f"Masked branch: {branch.name} ({branch.id})")
        print(f"Verified: no PII detector hits (sampled up to {args.sample} rows per text column)")
        if not deleted:
            print(f"Connect: {url}")
    if not args.pretty:
        output_json({
            "branch": {"name": branch.name, "id": branch.id,
                       "url": None if deleted else url, "deleted": deleted},
            "masked": masked,
            "leaks": [_leak(lk) for lk in leaks],
            "sample": args.sample,
        })
    return 1 if leaks else 0


def _leak(lk: Leak) -> dict:
    return {"table": lk.table, "column": lk.column, "detector": lk.detector,
            "hits": lk.hits, "example": lk.example}


if __name__ == "__main__":
    raise SystemExit(main())
