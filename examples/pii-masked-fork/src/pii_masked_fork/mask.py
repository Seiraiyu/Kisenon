"""mask.yaml -> masking statements on the fork, then regex leak detection."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from psycopg import sql

SQL_STRATEGIES = ("hash", "null", "redact")


class SpecError(ValueError):
    """mask.yaml is malformed, or the table can't be masked as asked."""


@dataclass(slots=True)
class MaskSpec:
    schema: str
    tables: dict[str, dict[str, str]]  # table -> column -> strategy


def _valid_faker(strategy: str) -> bool:
    if not strategy.startswith("faker:"):
        return False
    from faker import Faker
    return callable(getattr(Faker(), strategy.removeprefix("faker:"), None))


def load_spec(path: str | Path) -> MaskSpec:
    data = yaml.safe_load(Path(path).read_text()) or {}
    schema, tables = data.get("schema"), data.get("tables")
    if not isinstance(schema, str) or not schema:
        raise SpecError(f"{path}: `schema:` is required")
    if not isinstance(tables, dict) or not tables:
        raise SpecError(f"{path}: `tables:` must map table -> column -> strategy")
    out: dict[str, dict[str, str]] = {}
    for table, cols in tables.items():
        if not isinstance(cols, dict) or not cols:
            raise SpecError(f"{path}: table {table!r} needs at least one column")
        out[str(table)] = {}
        for col, strategy in cols.items():
            s = "null" if strategy is None else str(strategy)
            if s not in SQL_STRATEGIES and not _valid_faker(s):
                raise SpecError(
                    f"{path}: {table}.{col}: unknown strategy {s!r} "
                    "(use hash | null | redact | faker:<provider>)"
                )
            out[str(table)][str(col)] = s
    return MaskSpec(schema=schema, tables=out)


def update_sql(schema: str, table: str, columns: dict[str, str]) -> sql.Composed | None:
    """One UPDATE covering every hash/null/redact column of `table` (faker is separate)."""
    sets = []
    for col, strategy in columns.items():
        c = sql.Identifier(col)
        if strategy == "hash":
            expr = sql.SQL("md5({}::text)").format(c)
        elif strategy == "null":
            expr = sql.SQL("NULL")
        elif strategy == "redact":
            expr = sql.SQL("CASE WHEN {} IS NULL THEN NULL ELSE 'REDACTED' END").format(c)
        else:
            continue
        sets.append(sql.SQL("{} = {}").format(c, expr))
    if not sets:
        return None
    return sql.SQL("UPDATE {} SET {}").format(
        sql.Identifier(schema, table), sql.SQL(", ").join(sets)
    )
