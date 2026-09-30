"""Compare dbt relations (row counts + columns) between main and a fork."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from psycopg2 import sql

# name -> (row count, {column: data_type}); rows is None when the relation is missing
Snapshot = dict[str, tuple[int | None, dict[str, str]]]


@dataclass(slots=True)
class Relation:
    name: str
    schema: str
    alias: str


@dataclass(slots=True)
class ModelDiff:
    name: str
    main_rows: int | None
    fork_rows: int | None
    added_columns: list[str]
    removed_columns: list[str]
    changed_types: list[str]

    @property
    def delta_pct(self) -> float | None:
        if self.main_rows is None or self.fork_rows is None:
            return None
        if self.main_rows == 0:
            return 0.0 if self.fork_rows == 0 else 100.0
        return (self.fork_rows - self.main_rows) / self.main_rows * 100


def relations_from_manifest(path: Path) -> list[Relation]:
    """Models and seeds dbt built (ephemeral models have no relation)."""
    nodes = json.loads(path.read_text())["nodes"].values()
    return sorted(
        (
            Relation(name=n["name"], schema=n["schema"], alias=n["alias"])
            for n in nodes
            if n["resource_type"] in ("model", "seed")
            and n["config"].get("materialized") != "ephemeral"
        ),
        key=lambda r: r.name,
    )


def snapshot(conn, relations: list[Relation]) -> Snapshot:
    out: Snapshot = {}
    with conn.cursor() as cur:
        for rel in relations:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                (rel.schema, rel.alias),
            )
            columns = dict(cur.fetchall())
            if not columns:
                out[rel.name] = (None, {})
                continue
            cur.execute(sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(rel.schema), sql.Identifier(rel.alias)))
            out[rel.name] = (cur.fetchone()[0], columns)
    return out


def diff(main: Snapshot, fork: Snapshot) -> list[ModelDiff]:
    result = []
    for name in sorted(fork):
        main_rows, main_cols = main.get(name, (None, {}))
        fork_rows, fork_cols = fork[name]
        result.append(ModelDiff(
            name=name,
            main_rows=main_rows,
            fork_rows=fork_rows,
            added_columns=[c for c in fork_cols if c not in main_cols] if main_cols else [],
            removed_columns=[c for c in main_cols if c not in fork_cols],
            changed_types=[
                f"{c}: {main_cols[c]} -> {t}"
                for c, t in fork_cols.items() if c in main_cols and main_cols[c] != t
            ],
        ))
    return result


def failures(diffs: list[ModelDiff], max_row_delta_pct: float) -> list[str]:
    """Breaking changes fail CI; new models and added columns do not."""
    out = []
    for d in diffs:
        if d.fork_rows is None:
            out.append(f"{d.name}: missing on the fork")
        if d.removed_columns:
            out.append(f"{d.name}: removed columns {', '.join(d.removed_columns)}")
        for change in d.changed_types:
            out.append(f"{d.name}: type changed {change}")
        if d.delta_pct is not None and abs(d.delta_pct) > max_row_delta_pct:
            out.append(
                f"{d.name}: row count {d.main_rows} -> {d.fork_rows} "
                f"({d.delta_pct:+.1f}%, limit {max_row_delta_pct:g}%)"
            )
    return out


def render_table(diffs: list[ModelDiff]) -> str:
    lines = [f"{'model':<16}{'main':>8}{'fork':>8}{'delta':>9}  schema"]
    for d in diffs:
        if d.main_rows is None:
            delta = "new"
        else:
            delta = "-" if d.delta_pct is None else f"{d.delta_pct:+.1f}%"
        schema = "; ".join(
            [f"+{c}" for c in d.added_columns]
            + [f"-{c}" for c in d.removed_columns]
            + d.changed_types
        )
        main_rows = "-" if d.main_rows is None else str(d.main_rows)
        fork_rows = "-" if d.fork_rows is None else str(d.fork_rows)
        lines.append(f"{d.name:<16}{main_rows:>8}{fork_rows:>8}{delta:>9}  {schema}")
    return "\n".join(lines)
