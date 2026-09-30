from seed_snapshots import seed as seed_mod


class FakeCursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        self.log.append((query.split()[0:3], params))


class FakeConn:
    def __init__(self):
        self.log = []
        self.committed = False

    def cursor(self):
        return FakeCursor(self.log)

    def commit(self):
        self.committed = True


def test_small_fixture_inserts_users_then_orders_and_commits():
    conn = FakeConn()
    seed_mod.seed(conn, "small")
    assert conn.log[1] == (["INSERT", "INTO", "seed_snapshots.users"], {"users": 100})
    assert conn.log[2] == (["INSERT", "INTO", "seed_snapshots.orders"],
                           {"users": 100, "orders": 1_000})
    assert conn.log[-1][0][0] == "ANALYZE"
    assert conn.committed


def test_empty_fixture_is_schema_only():
    conn = FakeConn()
    seed_mod.seed(conn, "empty")
    assert [q[0][0] for q in conn.log] == ["DROP", "ANALYZE"]


def test_orders_sql_escapes_modulo_for_psycopg():
    # psycopg treats a bare % as a placeholder; every modulo must be %%
    assert "%%" in seed_mod.ORDERS_SQL
    assert "% " not in seed_mod.ORDERS_SQL.replace("%%", "")


def test_fixture_sizes_grow():
    sizes = [seed_mod.FIXTURES[f][1] for f in ("empty", "small", "prodlike")]
    assert sizes == sorted(sizes) and sizes[0] == 0
