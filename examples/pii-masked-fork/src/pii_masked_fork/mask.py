"""mask.yaml -> masking statements on the fork, then regex leak detection."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


# Values that look like PII after masking. Faker's safe_email uses example.com/org/net,
# so those domains are allowed. Phone needs separators so md5 hex can't match.
DETECTORS = {
    "email": re.compile(r"[\w.+-]+@(?!example\.(?:com|org|net)\b)[\w-]+(?:\.[\w-]+)+"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\+?\d{1,3}[-. ]\d{3}[-. ]\d{3}[-. ]\d{4}\b"),
}


@dataclass(slots=True)
class Leak:
    table: str
    column: str
    detector: str
    hits: int
    example: str  # first 3 chars + *** — never print the full value


def connect(url: str, attempts: int = 10, delay_s: float = 2.0) -> Any:
    import psycopg
    for i in range(attempts):
        try:
            return psycopg.connect(url, autocommit=True)
        except psycopg.OperationalError:
            if i == attempts - 1:
                raise
            time.sleep(delay_s)
    raise AssertionError("unreachable")


def primary_key(conn: Any, schema: str, table: str) -> str:
    rows = conn.execute(
        "SELECT a.attname FROM pg_index i JOIN pg_attribute a "
        "ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = %s::regclass AND i.indisprimary",
        (sql.Identifier(schema, table).as_string(None),),
    ).fetchall()
    if len(rows) != 1:
        raise SpecError(f"{schema}.{table}: faker masking needs a single-column primary key")
    return rows[0][0]


def faker_values(provider: str, keys: list[Any], seed: int = 0) -> list[tuple[str, str]]:
    from faker import Faker
    fake = Faker()
    fake.seed_instance(seed)
    gen = getattr(fake, provider)
    return [(str(k), str(gen())) for k in keys]


def apply_faker(conn: Any, schema: str, table: str, col: str, provider: str) -> int:
    pk = primary_key(conn, schema, table)
    t, c, k = sql.Identifier(schema, table), sql.Identifier(col), sql.Identifier(pk)
    keys = [r[0] for r in conn.execute(
        sql.SQL("SELECT {} FROM {} WHERE {} IS NOT NULL").format(k, t, c)
    ).fetchall()]
    rows = faker_values(provider, keys)
    with conn.transaction():
        conn.execute("CREATE TEMP TABLE _mask (k text PRIMARY KEY, v text) ON COMMIT DROP")
        with conn.cursor() as cur, cur.copy("COPY _mask (k, v) FROM STDIN") as cp:
            for row in rows:
                cp.write_row(row)
        conn.execute(sql.SQL("UPDATE {t} SET {c} = _mask.v FROM _mask WHERE {t}.{k}::text = _mask.k")
                     .format(t=t, c=c, k=k))
    return len(rows)


def apply_mask(conn: Any, spec: MaskSpec) -> dict[str, int]:
    """Mask every configured column; return rows touched per `table.column`."""
    done: dict[str, int] = {}
    for table, cols in spec.tables.items():
        stmt = update_sql(spec.schema, table, cols)
        if stmt is not None:
            n = conn.execute(stmt).rowcount
            done.update({f"{table}.{c}": n for c, s in cols.items() if not s.startswith("faker:")})
        for col, s in cols.items():
            if s.startswith("faker:"):
                done[f"{table}.{col}"] = apply_faker(
                    conn, spec.schema, table, col, s.removeprefix("faker:")
                )
    return done


def find_leaks(values: list[str]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for v in values:
        for name, rx in DETECTORS.items():
            if rx.search(v):
                hits.setdefault(name, []).append(v)
    return hits


def verify(conn: Any, schema: str, sample: int) -> list[Leak]:
    """Sample up to `sample` non-null values of EVERY text column in `schema`."""
    cols = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND data_type IN ('text', 'character varying', 'character') "
        "ORDER BY table_name, ordinal_position",
        (schema,),
    ).fetchall()
    leaks: list[Leak] = []
    for table, col in cols:
        q = sql.SQL("SELECT {c} FROM {t} WHERE {c} IS NOT NULL ORDER BY random() LIMIT %s").format(
            c=sql.Identifier(col), t=sql.Identifier(schema, table)
        )
        values = [str(r[0]) for r in conn.execute(q, (sample,)).fetchall()]
        for detector, found in find_leaks(values).items():
            leaks.append(Leak(table, col, detector, len(found), found[0][:3] + "***"))
    return leaks
