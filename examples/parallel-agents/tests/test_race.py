import asyncio
from collections import Counter
from unittest.mock import MagicMock

import parallel_agents.race as race
from parallel_agents.keon import Branch, KeonError
from parallel_agents.race import STRATEGIES, Candidate, pick_winner, run_candidate


def _patch_fork(monkeypatch, *, rows_after=None, create_error=None):
    monkeypatch.setattr(race, "find_branch_id", lambda project, name: "main_id")

    def create(project, name, parent_id):
        if create_error:
            raise create_error
        return Branch(name=name, id=f"id-{name}", created_in_ms=3)
    monkeypatch.setattr(race, "create_branch", create)
    monkeypatch.setattr(race, "get_branch_url", lambda project, branch: "postgresql://f")
    conn = MagicMock()
    monkeypatch.setattr(race, "connect", lambda url: conn)
    baseline = Counter({("2026-06-01", "view", 3): 1})
    results = iter([baseline, rows_after if rows_after is not None else baseline])
    monkeypatch.setattr(race, "rows_of", lambda c, q: next(results))
    times = iter([80.0, 0.5])
    monkeypatch.setattr(race, "time_query", lambda c, q: next(times))
    monkeypatch.setattr(race, "explain_text", lambda c, q: "Seq Scan on events")
    monkeypatch.setattr(race, "describe_schema", lambda c: "events(id bigint)")
    return conn


def test_run_candidate_happy_path(monkeypatch):
    conn = _patch_fork(monkeypatch)
    created: list[Branch] = []
    prompts = []

    def ask(system, user):
        prompts.append((system, user))
        return ('```json\n{"setup_sql": ["CREATE INDEX ON events (account_id, created_at)"],'
                ' "query": "SELECT 1;", "rationale": "composite index"}\n```')

    c = run_candidate("index", project="p", name="pa-x-index", query="SELECT 0",
                      goal_ms=5, ask=ask, created=created)
    assert c.error is None
    assert (c.baseline_ms, c.after_ms, c.correct) == (80.0, 0.5, True)
    assert c.query == "SELECT 1"
    assert c.setup_sql == ["CREATE INDEX ON events (account_id, created_at)"]
    assert [b.name for b in created] == ["pa-x-index"]
    conn.execute.assert_any_call("CREATE INDEX ON events (account_id, created_at)")
    assert STRATEGIES["index"] in prompts[0][0]
    assert "80.0 ms" in prompts[0][1]
    conn.close.assert_called_once()


def test_run_candidate_marks_wrong_rows(monkeypatch):
    _patch_fork(monkeypatch, rows_after=Counter())
    c = run_candidate("rewrite", project="p", name="n", query="SELECT 0", goal_ms=5,
                      ask=lambda s, u: '{"setup_sql": [], "query": "SELECT 2"}', created=[])
    assert c.correct is False and c.error is None


def test_run_candidate_captures_errors(monkeypatch):
    _patch_fork(monkeypatch, create_error=KeonError("quota"))
    created: list[Branch] = []
    c = run_candidate("matview", project="p", name="n", query="q", goal_ms=5,
                      ask=lambda s, u: "{}", created=created)
    assert c.error == "KeonError: quota"
    assert c.branch is None and created == []


def test_pick_winner_fastest_correct_only():
    a = Candidate(strategy="index", correct=True, after_ms=0.4)
    b = Candidate(strategy="matview", correct=False, after_ms=0.1)
    c = Candidate(strategy="rewrite", correct=True, after_ms=70.0)
    d = Candidate(strategy="x", error="boom")
    assert pick_winner([a, b, c, d]) is a
    assert pick_winner([b, d]) is None


def test_race_runs_every_strategy_concurrently(monkeypatch):
    seen = []

    def fake_run(strategy, **kw):
        seen.append((strategy, kw["name"]))
        return Candidate(strategy=strategy)
    monkeypatch.setattr(race, "run_candidate", fake_run)
    out = asyncio.run(race.race(["index", "rewrite"], project="p", run_id="ab12", query="q",
                                goal_ms=5, ask=lambda s, u: "", created=[]))
    assert [c.strategy for c in out] == ["index", "rewrite"]
    assert sorted(seen) == [("index", "parallel-agents-ab12-index"),
                            ("rewrite", "parallel-agents-ab12-rewrite")]
