"""Capture schema via `pg_dump --schema-only` and line-diff two captures."""
from __future__ import annotations

import difflib
import re
import subprocess


class PgDumpNotFound(RuntimeError):
    """`pg_dump` binary isn't on PATH."""


# Timestamps and version markers introduce noise that isn't a real schema
# change. We strip lines matching these patterns before diffing.
_NOISE_PATTERNS = [
    re.compile(r"^-- Dumped from database version .*$", re.MULTILINE),
    re.compile(r"^-- Dumped by pg_dump version .*$", re.MULTILINE),
    re.compile(r"^-- Started on .*$", re.MULTILINE),
    re.compile(r"^-- Completed on .*$", re.MULTILINE),
]


def strip_noise(text: str) -> str:
    out = text
    for pat in _NOISE_PATTERNS:
        out = pat.sub("", out)
    # Collapse runs of blank lines and trim trailing blank lines.
    out = re.sub(r"\n\n+", "\n\n", out).rstrip() + "\n"
    return out


def capture_schema(connection_url: str) -> str:
    try:
        proc = subprocess.run(
            [
                "pg_dump",
                "--schema-only",
                "--no-owner",
                "--no-acl",
                connection_url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise PgDumpNotFound(
            "`pg_dump` is not on PATH. Install Postgres 17 client tools "
            "(e.g. `apt install postgresql-client-17`)."
        ) from e
    if proc.returncode != 0:
        raise RuntimeError(
            f"pg_dump failed ({proc.returncode}): {(proc.stderr or '').strip()}"
        )
    return strip_noise(proc.stdout)


def compute_diff(before: str, after: str) -> str:
    """Return a unified diff string, or "" if the inputs are identical."""
    if before == after:
        return ""
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile="before",
        tofile="after",
        n=3,
    )
    return "".join(diff)
