from pathlib import Path

import pytest

from pii_masked_fork.mask import MaskSpec, SpecError, load_spec, update_sql

EXAMPLE_DIR = Path(__file__).resolve().parents[1]


def test_load_shipped_spec():
    spec = load_spec(EXAMPLE_DIR / "mask.yaml")
    assert spec == MaskSpec(schema="pii_masked_fork", tables={"customers": {
        "email": "faker:safe_email", "full_name": "faker:name", "phone": "redact",
        "ssn": "null", "loyalty_id": "hash", "notes": "redact",
    }})


def test_bare_yaml_null_means_null_strategy(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text("schema: s\ntables:\n  t:\n    c: null\n")
    assert load_spec(p).tables == {"t": {"c": "null"}}


@pytest.mark.parametrize("body, msg", [
    ("tables: {t: {c: hash}}", "`schema:` is required"),
    ("schema: s", "`tables:` must map"),
    ("schema: s\ntables:\n  t: {}", "needs at least one column"),
    ("schema: s\ntables:\n  t: {c: shuffle}", "unknown strategy 'shuffle'"),
    ("schema: s\ntables:\n  t: {c: 'faker:not_a_provider'}", "unknown strategy"),
])
def test_load_rejects_bad_specs(tmp_path, body, msg):
    p = tmp_path / "m.yaml"
    p.write_text(body)
    with pytest.raises(SpecError, match=msg):
        load_spec(p)


def test_update_sql_covers_sql_strategies_only():
    stmt = update_sql("pii_masked_fork", "customers", {
        "email": "faker:safe_email", "phone": "redact", "ssn": "null", "loyalty_id": "hash",
    })
    assert stmt.as_string(None) == (
        'UPDATE "pii_masked_fork"."customers" SET '
        '"phone" = CASE WHEN "phone" IS NULL THEN NULL ELSE \'REDACTED\' END, '
        '"ssn" = NULL, '
        '"loyalty_id" = md5("loyalty_id"::text)'
    )


def test_update_sql_none_when_only_faker():
    assert update_sql("s", "t", {"c": "faker:name"}) is None
