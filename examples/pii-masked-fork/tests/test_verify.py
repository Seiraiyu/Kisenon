from unittest.mock import MagicMock

import psycopg

import pii_masked_fork.mask as mask
from pii_masked_fork.mask import MaskSpec, apply_mask, faker_values, find_leaks, verify


def test_faker_values_are_deterministic_and_safe():
    a = faker_values("safe_email", [1, 2, 3], seed=7)
    b = faker_values("safe_email", [1, 2, 3], seed=7)
    assert a == b
    assert [k for k, _ in a] == ["1", "2", "3"]
    assert all(v.split("@")[1].startswith("example.") for _, v in a)


def test_find_leaks_detectors():
    values = [
        "person10@acme-mail.com",           # email leak
        "someone@example.org",              # allowed (faker safe_email domain)
        "Call back on +1-555-037-0042",     # phone leak
        "123-45-6789",                      # ssn leak
        "REDACTED",
        "5d41402abc4b2a76b9719d911017c592",  # md5 hex: no hit
        "Loyal customer",
    ]
    hits = find_leaks(values)
    assert hits == {
        "email": ["person10@acme-mail.com"],
        "phone": ["Call back on +1-555-037-0042"],
        "ssn": ["123-45-6789"],
    }


def _cursor(rows=None, rowcount=0):
    cur = MagicMock()
    cur.fetchall.return_value = rows or []
    cur.rowcount = rowcount
    return cur


def test_verify_samples_every_text_column_and_reports_leaks():
    conn = MagicMock()
    conn.execute.side_effect = [
        _cursor([("customers", "email"), ("customers", "notes")]),
        _cursor([("a@example.com",)]),
        _cursor([("Prefers email at person10@acme-mail.com",), ("Loyal customer",)]),
    ]
    leaks = verify(conn, "pii_masked_fork", sample=100)
    assert len(leaks) == 1
    leak = leaks[0]
    assert (leak.table, leak.column, leak.detector, leak.hits) == ("customers", "notes", "email", 1)
    assert leak.example == "Pre***"
    assert conn.execute.call_args_list[1].args[1] == (100,)


def test_apply_mask_runs_sql_update_then_faker_columns(monkeypatch):
    conn = MagicMock()
    conn.execute.return_value = _cursor(rowcount=5000)
    faker_calls = []

    def fake_apply_faker(c, schema, table, col, provider):
        faker_calls.append((table, col, provider))
        return 5000
    monkeypatch.setattr(mask, "apply_faker", fake_apply_faker)
    done = apply_mask(conn, MaskSpec("s", {"customers": {
        "email": "faker:safe_email", "phone": "redact", "ssn": "null"}}))
    assert done == {"customers.phone": 5000, "customers.ssn": 5000, "customers.email": 5000}
    assert faker_calls == [("customers", "email", "safe_email")]


def test_apply_faker_copies_values_and_updates(monkeypatch):
    conn = MagicMock()
    conn.execute.return_value = _cursor(rows=[(1,), (2,)])
    monkeypatch.setattr(mask, "primary_key", lambda c, s, t: "id")
    copy = conn.cursor.return_value.__enter__.return_value.copy.return_value.__enter__.return_value
    n = mask.apply_faker(conn, "s", "customers", "email", "safe_email")
    assert n == 2
    assert copy.write_row.call_count == 2
    last_sql = conn.execute.call_args_list[-1].args[0].as_string(None)
    assert last_sql.startswith('UPDATE "s"."customers" SET "email" = _mask.v FROM _mask')


def test_connect_retries(monkeypatch):
    attempts = []
    good = MagicMock()

    def fake_connect(url, autocommit):
        attempts.append(url)
        if len(attempts) < 2:
            raise psycopg.OperationalError("endpoint not found")
        return good
    monkeypatch.setattr(psycopg, "connect", fake_connect)
    monkeypatch.setattr(mask.time, "sleep", lambda s: None)
    assert mask.connect("postgresql://f") is good
