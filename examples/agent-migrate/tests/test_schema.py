import pytest

from agent_migrate.schema import NotReadOnly, guard_select


def test_guard_allows_select():
    guard_select("SELECT 1")
    guard_select("  with x as (select 1) select * from x")


def test_guard_rejects_write():
    with pytest.raises(NotReadOnly):
        guard_select("DELETE FROM users")
    with pytest.raises(NotReadOnly):
        guard_select("UPDATE users SET x = 1")


def test_guard_rejects_multistatement():
    with pytest.raises(NotReadOnly):
        guard_select("SELECT 1; DROP TABLE users")
