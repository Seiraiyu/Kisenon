import json

import pytest

from agent_memory.output import event, output_error, output_json


def test_event_formats_head_and_tail(capsys):
    event("fact added", text="User is vegetarian", sim=0.4)
    assert capsys.readouterr().err.strip() == "[fact added: User is vegetarian | sim=0.4]"


def test_event_bare_label(capsys):
    event("done")
    assert capsys.readouterr().err.strip() == "[done]"


def test_output_json_single_line(capsys):
    output_json({"a": 1})
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and json.loads(out) == {"a": 1}


def test_output_error_exits_with_code(capsys):
    with pytest.raises(SystemExit) as e:
        output_error("boom", {"hint": "x"}, exit_code=2)
    assert e.value.code == 2
    assert json.loads(capsys.readouterr().err) == {"error": "boom", "hint": "x"}
