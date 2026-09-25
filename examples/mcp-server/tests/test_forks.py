import pytest

from kisenon_mcp import keon
from kisenon_mcp.forks import Registry, UnknownFork


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def fake_keon(monkeypatch):
    state = {"n": 0, "discarded": []}

    def create(*, project, ttl_s):
        state["n"] += 1
        return f"sb_{state['n']}", f"postgresql://fork{state['n']}"

    monkeypatch.setattr(keon, "sandbox_create", create)
    monkeypatch.setattr(keon, "sandbox_discard", lambda fid: state["discarded"].append(fid))
    return state


def test_create_and_get(fake_keon):
    reg = Registry(project=None, ttl_s=60, clock=Clock())
    fork = reg.create("idx-test")
    assert reg.get(fork.id).url == "postgresql://fork1"
    assert fork.public()["name"] == "idx-test"
    assert fork.public()["expires_at"].endswith("+00:00")


def test_unknown_fork_is_refused(fake_keon):
    reg = Registry(project=None, ttl_s=60)
    with pytest.raises(UnknownFork, match="fork_database"):
        reg.get("main")
    with pytest.raises(UnknownFork):
        reg.destroy("sb_999")
    assert fake_keon["discarded"] == []


def test_reap_destroys_only_expired(fake_keon):
    clock = Clock()
    reg = Registry(project=None, ttl_s=60, clock=clock)
    old = reg.create()
    clock.now += 30
    young = reg.create()
    clock.now += 31  # old is 61s old, young 31s
    assert reg.reap() == [old.id]
    assert fake_keon["discarded"] == [old.id]
    assert [f.id for f in reg.list()] == [young.id]


def test_destroy_all_on_shutdown(fake_keon):
    reg = Registry(project=None, ttl_s=60)
    a, b = reg.create(), reg.create()
    reg.destroy_all()
    assert fake_keon["discarded"] == [a.id, b.id] and reg.list() == []


def test_discard_failure_is_logged_not_raised(monkeypatch, capsys, fake_keon):
    def boom(fid):
        raise keon.KeonError("503")

    reg = Registry(project=None, ttl_s=60)
    reg.create()
    monkeypatch.setattr(keon, "sandbox_discard", boom)
    reg.destroy_all()
    assert "keon sandbox discard sb_1" in capsys.readouterr().err
