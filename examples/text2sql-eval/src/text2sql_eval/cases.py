"""Eval cases (YAML) and scoring."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml


class CaseFileError(ValueError):
    """cases.yaml is malformed."""


@dataclass(slots=True)
class Case:
    id: str
    question: str
    expected_rows: list[list[Any]] | None = None
    expected_rowcount: int | None = None
    ordered: bool = False


@dataclass(slots=True)
class Outcome:
    sql: str
    rows: list[tuple] | None  # None when the statement returned no result set
    rowcount: int | None
    status: str  # psycopg statusmessage, e.g. "SELECT 3", "DELETE 100"
    error: str | None
    duration_ms: int


def load_cases(path: str | Path) -> list[Case]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    raw = data.get("cases")
    if not isinstance(raw, list) or not raw:
        raise CaseFileError(f"{path}: expected a non-empty `cases:` list")
    cases: list[Case] = []
    seen: set[str] = set()
    for i, c in enumerate(raw, start=1):
        if not isinstance(c, dict) or not c.get("id") or not c.get("question"):
            raise CaseFileError(f"{path}: case #{i} needs `id` and `question`")
        if ("expected_rows" in c) == ("expected_rowcount" in c):
            raise CaseFileError(
                f"{path}: case {c['id']!r} needs exactly one of expected_rows / expected_rowcount"
            )
        if c["id"] in seen:
            raise CaseFileError(f"{path}: duplicate case id {c['id']!r}")
        seen.add(c["id"])
        cases.append(Case(
            id=str(c["id"]),
            question=str(c["question"]),
            expected_rows=c.get("expected_rows"),
            expected_rowcount=c.get("expected_rowcount"),
            ordered=bool(c.get("ordered", False)),
        ))
    return cases


def _norm(v: Any) -> Any:
    if v is None or isinstance(v, bool | str):
        return v
    if isinstance(v, int | float | Decimal):
        d = Decimal(str(v))
        return int(d) if d == d.to_integral_value() else round(float(d), 4)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def normalize_row(row: tuple | list) -> tuple:
    return tuple(_norm(v) for v in row)


def score(case: Case, o: Outcome) -> tuple[str | None, str]:
    """Return (match_kind, reason). match_kind is exact|set|rowcount, or None on fail."""
    if o.error:
        return None, f"error: {o.error}"
    if case.expected_rowcount is not None:
        if o.rows is not None:
            return None, "expected a write, got a result set"
        if o.rowcount == case.expected_rowcount:
            return "rowcount", f"rowcount {o.rowcount}"
        return None, f"rowcount {o.rowcount}, expected {case.expected_rowcount}"
    if o.rows is None:
        return None, "expected rows, got a write"
    got = [normalize_row(r) for r in o.rows]
    want = [normalize_row(r) for r in case.expected_rows or []]
    if got == want:
        return "exact", "exact match"
    if case.ordered:
        return None, "rows differ (order matters)"
    if Counter(got) == Counter(want):
        return "set", "same rows, other order"
    return None, "rows differ"
