from unittest.mock import MagicMock

from agent_sandbox.db import RunSqlResult
from agent_sandbox.loop import LoopOptions, LoopResult, QueryRecord, run_ask
from agent_sandbox.providers.base import ToolCall, TurnResult


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls: list[tuple[list[dict], list[dict]]] = []

    def run_turn(self, messages, tools):
        self.calls.append((messages, tools))
        return self._turns.pop(0)

    def encode_user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def encode_tool_result(self, tool_call_id: str, result_text: str) -> dict:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result_text}


def _result_for(sql: str, **overrides):
    base = dict(
        sql=sql,
        rows_returned=1,
        rows_truncated=False,
        duration_ms=5,
        result_preview=[{"count": 1}],
        error=None,
    )
    base.update(overrides)
    return RunSqlResult(**base)


def test_loop_options_defaults():
    opts = LoopOptions(question="how many users?", provider_name="anthropic", model=None)
    assert opts.max_queries == 10
    assert opts.max_wall_s == 120
    assert opts.row_cap == 1000
    assert opts.always_delete is False


def test_query_record_dataclass_shape():
    q = QueryRecord(
        iteration=1,
        sql="SELECT 1",
        rows_returned=1,
        rows_truncated=False,
        duration_ms=5,
        result_preview=[{"?column?": 1}],
        error=None,
    )
    assert q.iteration == 1


def test_loop_result_dataclass_shape():
    r = LoopResult(
        answer="3,142 users.",
        queries=[],
        cap_hit=None,
        provider="anthropic",
        model="claude-sonnet-4-6",
        branch_name="agent-sandbox-x",
        branch_id="br_x",
        branch_url="postgresql://x",
        branch_created_in_ms=547,
        branch_deleted=True,
        branch_delete_skipped_reason=None,
        total_duration_ms=2102,
    )
    assert r.answer == "3,142 users."


def test_run_ask_calls_tool_then_returns_answer(monkeypatch):
    fake = FakeProvider([
        TurnResult(
            text=None,
            tool_calls=[ToolCall("t1", "run_sql", {"sql": "SELECT count(*) FROM users"})],
        ),
        TurnResult(text="There are 12,340 users.", tool_calls=[]),
    ])
    monkeypatch.setattr(
        "agent_sandbox.loop._fork_branch",
        lambda project, name: ("br_id", "postgresql://x", 500),
    )
    monkeypatch.setattr("agent_sandbox.loop._open_connection", lambda url: MagicMock())
    deleted: list[str] = []
    monkeypatch.setattr(
        "agent_sandbox.loop._delete_branch",
        lambda branch_id: deleted.append(branch_id),
    )
    monkeypatch.setattr(
        "agent_sandbox.loop.run_sql",
        lambda conn, sql, row_cap: _result_for(sql),
    )

    opts = LoopOptions(
        question="how many users?",
        provider_name="fake",
        model=None,
        project="proj_x",
        branch_name="agent-sandbox-x",
    )
    result = run_ask(opts, provider=fake)

    assert result.answer == "There are 12,340 users."
    assert result.cap_hit is None
    assert len(result.queries) == 1
    assert result.queries[0].sql == "SELECT count(*) FROM users"
    assert result.queries[0].iteration == 1
    assert result.branch_deleted is True
    assert deleted == ["br_id"]


def test_run_ask_max_queries_cap_triggers_summary_turn(monkeypatch):
    fake = FakeProvider([
        TurnResult(text=None, tool_calls=[ToolCall("t1", "run_sql", {"sql": "SELECT 1"})]),
        TurnResult(text=None, tool_calls=[ToolCall("t2", "run_sql", {"sql": "SELECT 2"})]),
        TurnResult(text="Partial answer based on 2 queries.", tool_calls=[]),
    ])
    monkeypatch.setattr(
        "agent_sandbox.loop._fork_branch",
        lambda project, name: ("br_id", "postgresql://x", 500),
    )
    monkeypatch.setattr("agent_sandbox.loop._open_connection", lambda url: MagicMock())
    monkeypatch.setattr("agent_sandbox.loop._delete_branch", lambda branch_id: None)
    monkeypatch.setattr(
        "agent_sandbox.loop.run_sql",
        lambda conn, sql, row_cap: _result_for(sql),
    )

    opts = LoopOptions(
        question="hard one",
        provider_name="fake",
        model=None,
        project="proj_x",
        branch_name="agent-sandbox-y",
        max_queries=2,
    )
    result = run_ask(opts, provider=fake)

    assert result.cap_hit == "max_queries"
    assert result.answer == "Partial answer based on 2 queries."
    assert len(result.queries) == 2
    assert result.branch_deleted is False
    assert result.branch_delete_skipped_reason == "cap_hit: max_queries"
    last_call_tools = fake.calls[-1][1]
    assert last_call_tools == []


def test_run_ask_max_wall_cap_triggers_summary(monkeypatch):
    fake = FakeProvider([
        TurnResult(text=None, tool_calls=[ToolCall("t1", "run_sql", {"sql": "SELECT 1"})]),
        TurnResult(text="Summarized from one slow query.", tool_calls=[]),
    ])
    timeline = iter([0.0, 200.0, 200.1, 200.2, 200.3])
    monkeypatch.setattr("agent_sandbox.loop.time.monotonic", lambda: next(timeline))
    monkeypatch.setattr(
        "agent_sandbox.loop._fork_branch",
        lambda project, name: ("br_id", "postgresql://x", 500),
    )
    monkeypatch.setattr("agent_sandbox.loop._open_connection", lambda url: MagicMock())
    monkeypatch.setattr("agent_sandbox.loop._delete_branch", lambda branch_id: None)
    monkeypatch.setattr(
        "agent_sandbox.loop.run_sql",
        lambda conn, sql, row_cap: _result_for(sql),
    )

    opts = LoopOptions(
        question="slow",
        provider_name="fake",
        model=None,
        project="proj_x",
        branch_name="agent-sandbox-z",
        max_queries=20,
        max_wall_s=10,
    )
    result = run_ask(opts, provider=fake)

    assert result.cap_hit == "max_wall_s"
    assert result.answer == "Summarized from one slow query."
    assert result.branch_deleted is False


def test_run_ask_always_delete_overrides_cap_preservation(monkeypatch):
    fake = FakeProvider([
        TurnResult(text=None, tool_calls=[ToolCall("t1", "run_sql", {"sql": "SELECT 1"})]),
        TurnResult(text="summary", tool_calls=[]),
    ])
    monkeypatch.setattr(
        "agent_sandbox.loop._fork_branch",
        lambda project, name: ("br_id", "postgresql://x", 500),
    )
    monkeypatch.setattr("agent_sandbox.loop._open_connection", lambda url: MagicMock())
    deleted: list[str] = []
    monkeypatch.setattr(
        "agent_sandbox.loop._delete_branch",
        lambda branch_id: deleted.append(branch_id),
    )
    monkeypatch.setattr(
        "agent_sandbox.loop.run_sql",
        lambda conn, sql, row_cap: _result_for(sql),
    )

    opts = LoopOptions(
        question="capped",
        provider_name="fake",
        model=None,
        project="proj_x",
        branch_name="agent-sandbox-a",
        max_queries=1,
        always_delete=True,
    )
    result = run_ask(opts, provider=fake)
    assert result.cap_hit == "max_queries"
    assert result.branch_deleted is True
    assert deleted == ["br_id"]


def test_run_ask_tool_error_is_passed_back_loop_continues(monkeypatch):
    fake = FakeProvider([
        TurnResult(
            text=None,
            tool_calls=[ToolCall("t1", "run_sql", {"sql": "SELECT * FROOM users"})],
        ),
        TurnResult(
            text=None,
            tool_calls=[ToolCall("t2", "run_sql", {"sql": "SELECT * FROM users"})],
        ),
        TurnResult(text="Worked the second time.", tool_calls=[]),
    ])
    monkeypatch.setattr(
        "agent_sandbox.loop._fork_branch",
        lambda project, name: ("br_id", "postgresql://x", 500),
    )
    monkeypatch.setattr("agent_sandbox.loop._open_connection", lambda url: MagicMock())
    monkeypatch.setattr("agent_sandbox.loop._delete_branch", lambda branch_id: None)

    def fake_run_sql(conn, sql, row_cap):
        if "FROOM" in sql:
            return _result_for(sql, error="ProgrammingError: syntax error at or near 'FROOM'")
        return _result_for(sql)

    monkeypatch.setattr("agent_sandbox.loop.run_sql", fake_run_sql)

    opts = LoopOptions(
        question="anything",
        provider_name="fake",
        model=None,
        project="proj_x",
        branch_name="agent-sandbox-e",
    )
    result = run_ask(opts, provider=fake)
    assert len(result.queries) == 2
    assert result.queries[0].error is not None
    assert result.queries[1].error is None
    assert result.answer == "Worked the second time."
