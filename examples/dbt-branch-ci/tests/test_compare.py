import json

from dbt_branch_ci import compare
from dbt_branch_ci.compare import ModelDiff


def test_relations_from_manifest_keeps_models_and_seeds(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"nodes": {
        "model.j.orders": {"resource_type": "model", "name": "orders", "schema": "s",
                           "alias": "orders", "config": {"materialized": "table"}},
        "model.j.eph": {"resource_type": "model", "name": "eph", "schema": "s",
                        "alias": "eph", "config": {"materialized": "ephemeral"}},
        "seed.j.raw": {"resource_type": "seed", "name": "raw", "schema": "s",
                       "alias": "raw", "config": {"materialized": "seed"}},
        "test.j.t": {"resource_type": "test", "name": "t", "schema": "s_audit",
                     "alias": "t", "config": {"materialized": "test"}},
    }}))
    rels = compare.relations_from_manifest(manifest)
    assert [r.name for r in rels] == ["orders", "raw"]


def test_diff_detects_rows_and_schema_changes():
    main = {"orders": (30, {"order_id": "integer", "status": "text", "amount": "numeric"})}
    fork = {
        "orders": (25, {"order_id": "bigint", "amount": "numeric", "note": "text"}),
        "new_model": (3, {"id": "integer"}),
    }
    d = {x.name: x for x in compare.diff(main, fork)}
    assert d["orders"].added_columns == ["note"]
    assert d["orders"].removed_columns == ["status"]
    assert d["orders"].changed_types == ["order_id: integer -> bigint"]
    assert round(d["orders"].delta_pct, 1) == -16.7
    assert d["new_model"].main_rows is None and d["new_model"].added_columns == []


def test_delta_pct_edge_cases():
    assert ModelDiff("m", 0, 0, [], [], []).delta_pct == 0.0
    assert ModelDiff("m", 0, 5, [], [], []).delta_pct == 100.0
    assert ModelDiff("m", None, 5, [], [], []).delta_pct is None


def test_failures_flag_breaking_changes_only():
    diffs = [
        ModelDiff("orders", 30, 25, [], [], []),        # -16.7% > 10%
        ModelDiff("customers", 10, 10, ["x"], [], []),  # added column: ok
        ModelDiff("new_model", None, 3, [], [], []),    # new model: ok
        ModelDiff("gone", 5, None, [], [], []),         # missing on fork
        ModelDiff("typed", 5, 5, [], ["a"], ["b: int -> text"]),
    ]
    out = compare.failures(diffs, 10)
    assert out == [
        "orders: row count 30 -> 25 (-16.7%, limit 10%)",
        "gone: missing on the fork",
        "typed: removed columns a",
        "typed: type changed b: int -> text",
    ]
    assert compare.failures(diffs[:3], 20) == []


def test_render_table_shows_new_and_delta():
    table = compare.render_table([
        ModelDiff("orders", 30, 25, [], [], []),
        ModelDiff("new_model", None, 3, ["id"], [], []),
    ])
    assert "-16.7%" in table
    assert "new" in table


class FakeCursor:
    def __init__(self, tables):
        self.tables = tables
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        if params:  # information_schema lookup
            self.result = list(self.tables.get(params[1], {}).items())
        else:
            self.result = [(7,)]

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0]


class FakeConn:
    def __init__(self, tables):
        self.tables = tables

    def cursor(self):
        return FakeCursor(self.tables)


def test_snapshot_counts_existing_and_marks_missing():
    rels = [compare.Relation("orders", "s", "orders"), compare.Relation("gone", "s", "gone")]
    snap = compare.snapshot(FakeConn({"orders": {"order_id": "integer"}}), rels)
    assert snap == {"orders": (7, {"order_id": "integer"}), "gone": (None, {})}
