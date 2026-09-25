import asyncio
import datetime

import pytest

from kisenon_mcp import keon, server
from kisenon_mcp.forks import Registry, UnknownFork

PLAN = [
    {"QUERY PLAN": "Index Scan using orders_customer_id_idx on orders  (actual time=0.02..0.03)"},
    {"QUERY PLAN": "Planning Time: 0.120 ms"},
    {"QUERY PLAN": "Execution Time: 0.045 ms"},
]


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self.rowcount = -1
        self._rows: list[dict] = []

    def execute(self, sql):
        self.conn.executed.append(sql)
        if sql.startswith("EXPLAIN"):
            self._rows, self.description = PLAN, [("QUERY PLAN",)]
        elif sql.startswith("SELECT"):
            self._rows = [{"id": i, "at": datetime.date(2026, 1, 1)}
                          for i in range(250)]
            self.description, self.rowcount = [("id",), ("at",)], 250
        else:
            self.rowcount = 42

    def fetchmany(self, n):
        return self._rows[:n]

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, url):
        self.url, self.executed = url, []

    def cursor(self):
        return FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def env(monkeypatch):
    state = {"discarded": [], "conns": []}
    monkeypatch.setattr(keon, "sandbox_create",
                        lambda *, project, ttl_s: ("sb_1", "postgresql://fork"))
    monkeypatch.setattr(keon, "sandbox_discard", lambda fid: state["discarded"].append(fid))
    monkeypatch.setattr(keon, "sandbox_diff", lambda fid: {"schema": [f"diff of {fid}"]})
    monkeypatch.setattr(server, "registry", Registry(project=None, ttl_s=1800))

    def connect(url):
        conn = FakeConn(url)
        state["conns"].append(conn)
        return conn

    monkeypatch.setattr(server, "_connect", connect)
    return state


def test_all_tools_are_registered():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {"fork_database", "run_sql", "explain_analyze", "schema_diff",
                     "destroy_fork", "list_forks"}


def test_fork_then_run_sql_caps_rows_at_200(env):
    fork = server.fork_database("demo")
    assert fork["fork_id"] == "sb_1" and fork["expires_at"]
    out = server.run_sql("sb_1", "SELECT * FROM big")
    assert len(out["rows"]) == 200 and out["truncated"] is True and out["rowcount"] == 250
    assert out["rows"][0] == {"id": 0, "at": "2026-01-01"}
    assert env["conns"][0].url == "postgresql://fork"


def test_run_sql_reports_rowcount_for_writes(env):
    server.fork_database()
    out = server.run_sql("sb_1", "DELETE FROM users")
    assert (out["rows"], out["rowcount"], out["truncated"]) == ([], 42, False)


def test_explain_analyze_parses_timings(env):
    server.fork_database()
    out = server.explain_analyze("sb_1", "SELECT 1")
    assert env["conns"][0].executed == ["EXPLAIN (ANALYZE, BUFFERS) SELECT 1"]
    assert (out["planning_ms"], out["execution_ms"]) == (0.12, 0.045)
    assert "Index Scan" in out["plan"]


def test_unknown_fork_is_refused_everywhere(env):
    for call in (lambda: server.run_sql("main", "SELECT 1"),
                 lambda: server.explain_analyze("main", "SELECT 1"),
                 lambda: server.schema_diff("main"),
                 lambda: server.destroy_fork("main")):
        with pytest.raises(UnknownFork):
            call()
    assert env["conns"] == [] and env["discarded"] == []


def test_schema_diff_list_and_destroy(env):
    server.fork_database("a")
    assert server.schema_diff("sb_1") == {"schema": ["diff of sb_1"]}
    assert [f["fork_id"] for f in server.list_forks()["forks"]] == ["sb_1"]
    assert server.destroy_fork("sb_1") == {"destroyed": "sb_1"}
    assert env["discarded"] == ["sb_1"] and server.list_forks() == {"forks": []}


def test_expired_fork_is_reaped_on_next_call(env):
    server.fork_database()
    fork = server.registry.get("sb_1")
    fork.expires_at = 0
    with pytest.raises(UnknownFork):
        server.run_sql("sb_1", "SELECT 1")
    assert env["discarded"] == ["sb_1"]
