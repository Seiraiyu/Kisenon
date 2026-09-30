from types import SimpleNamespace

from agent_memory import llm


def _resp(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class FakeClient:
    def __init__(self, text):
        self.calls = []
        self.messages = self
        self._text = text

    def create(self, **kw):
        self.calls.append(kw)
        return _resp(self._text)


def test_parse_facts_plain_array():
    assert llm.parse_facts('["User is vegetarian", "User lives in Lisbon"]') == [
        "User is vegetarian", "User lives in Lisbon",
    ]


def test_parse_facts_tolerates_prose_and_fences():
    assert llm.parse_facts('Sure:\n```json\n["User has a dog"]\n```') == ["User has a dog"]


def test_parse_facts_bad_json_or_empty():
    assert llm.parse_facts("nothing here") == []
    assert llm.parse_facts("[not json]") == []
    assert llm.parse_facts('["", 3, "ok"]') == ["ok"]


def test_extract_facts_uses_system_prompt():
    client = FakeClient('["User is vegetarian"]')
    assert llm.extract_facts(client, "m", "I'm vegetarian") == ["User is vegetarian"]
    assert client.calls[0]["system"] == llm.EXTRACT_PROMPT


def test_reply_puts_facts_in_system_and_history_before_message():
    client = FakeClient("Try the veggie place.")
    history = [("user", "hi"), ("assistant", "hey")]
    out = llm.reply(client, "m", "dinner?", ["User is vegetarian"], history)
    assert out == "Try the veggie place."
    kw = client.calls[0]
    assert "- User is vegetarian" in kw["system"]
    assert [m["role"] for m in kw["messages"]] == ["user", "assistant", "user"]
    assert kw["messages"][-1]["content"] == "dinner?"


def test_make_client_none_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.make_client() is None
