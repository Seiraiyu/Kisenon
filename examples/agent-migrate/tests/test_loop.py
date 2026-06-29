from agent_migrate import keon, loop
from agent_migrate.keon import SandboxRunResult
from agent_migrate.loop import LoopOptions, run_ask
from agent_migrate.providers.base import ToolCall, TurnResult


class FakeProvider:
    """Scripts a fixed sequence of turns; records messages it was given."""
    name = "anthropic"
    model = "fake-model"

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = 0

    def run_turn(self, messages, tools):
        t = self._turns[self.calls]
        self.calls += 1
        return t

    def encode_user_message(self, text):
        return {"role": "user", "content": text}

    def encode_tool_result(self, tool_call_id, result_text):
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result_text}


def _opts(**kw):
    base = dict(request="add status to orders", provider_name="anthropic", model=None,
                project="p", parent="main", kisenon_url="postgresql://x", max_attempts=3)
    base.update(kw)
    return LoopOptions(**base)


def _patch_env(monkeypatch, run_results):
    """Stub the live edges: schema conn, schema summary, and keon.sandbox_run."""
    monkeypatch.setattr(loop, "_open_readonly", lambda url: object())
    monkeypatch.setattr(loop, "_summarize", lambda conn: "orders(id integer, total numeric)")
    monkeypatch.setattr(loop, "_run_select", lambda conn, sql: [{"ok": 1}])
    seq = iter(run_results)
    monkeypatch.setattr(keon, "sandbox_run", lambda **kw: next(seq))


def _run_migration_call(i, mig="ALTER TABLE orders ADD COLUMN status text", ver="SELECT 1"):
    return TurnResult(text=None, tool_calls=[ToolCall(
        id=f"c{i}", name="run_migration", arguments={"migration_sql": mig, "verify_sql": ver})])


def _final(text):
    return TurnResult(text=text, tool_calls=[])


def test_green_first_try_offers_promote(monkeypatch):
    green = SandboxRunResult("sb_1", "green", [{"name": "verify", "exit_code": 0}],
                             [{"seq": 1, "statement": "ALTER ..."}], "keon sandbox promote sb_1")
    _patch_env(monkeypatch, [green])
    provider = FakeProvider([_run_migration_call(1), _final("Done; promote sb_1.")])
    result = run_ask(_opts(), provider=provider)
    assert result.final_status == "green"
    assert result.green_sandbox_id == "sb_1"
    assert result.promote_hint == "keon sandbox promote sb_1"
    assert result.promoted is None  # no --auto-promote


def test_red_then_green(monkeypatch):
    red = SandboxRunResult("sb_1", "red",
                           [{"name": "verify", "exit_code": 1, "stderr_tail": "null in status"}],
                           [], "red — sb_1 preserved")
    green = SandboxRunResult("sb_2", "green", [{"name": "verify", "exit_code": 0}],
                             [{"seq": 1}], "keon sandbox promote sb_2")
    _patch_env(monkeypatch, [red, green])
    provider = FakeProvider([_run_migration_call(1), _run_migration_call(2), _final("Fixed.")])
    result = run_ask(_opts(), provider=provider)
    assert result.final_status == "green"
    assert result.green_sandbox_id == "sb_2"
    assert len(result.attempts) == 2
    assert result.attempts[0].status == "red"


def test_cap_exhausted_is_red(monkeypatch):
    red = SandboxRunResult("sb_x", "red",
                           [{"name": "migrate", "exit_code": 1, "stderr_tail": "syntax"}],
                           [], "red — preserved")
    _patch_env(monkeypatch, [red, red, red])
    # model keeps trying; loop must stop after max_attempts run_migration calls
    provider = FakeProvider([_run_migration_call(1), _run_migration_call(2), _run_migration_call(3),
                             _final("giving up")])
    result = run_ask(_opts(max_attempts=3), provider=provider)
    assert result.final_status == "red"
    assert result.green_sandbox_id is None
    assert len(result.attempts) == 3


def test_auto_promote_promotes_green(monkeypatch):
    green = SandboxRunResult("sb_1", "green", [{"name": "verify", "exit_code": 0}],
                             [{"seq": 1}], "keon sandbox promote sb_1")
    _patch_env(monkeypatch, [green])
    monkeypatch.setattr(keon, "sandbox_promote", lambda **kw: {"id": "sb_1", "status": "promoted"})
    provider = FakeProvider([_run_migration_call(1), _final("done")])
    result = run_ask(_opts(auto_promote=True), provider=provider)
    assert result.promoted == "promoted"
