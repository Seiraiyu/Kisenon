import json
from unittest.mock import MagicMock

import pytest

import pii_masked_fork.cli as cli
from pii_masked_fork.keon import Branch
from pii_masked_fork.mask import Leak


def _patch(monkeypatch, *, leaks=(), apply_error=None):
    monkeypatch.setenv("KISENON_PROJECT_ID", "p")
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "find_branch_id", lambda project, name: "main_id")
    monkeypatch.setattr(cli, "create_branch",
                        lambda project, name, parent_id: Branch(name=name, id="br_1"))
    monkeypatch.setattr(cli, "get_branch_url", lambda project, branch: "postgresql://masked")
    monkeypatch.setattr(cli, "connect", lambda url: MagicMock())

    def fake_apply(conn, spec):
        if apply_error:
            raise apply_error
        return {"customers.email": 5000}
    monkeypatch.setattr(cli, "apply_mask", fake_apply)
    monkeypatch.setattr(cli, "verify", lambda conn, schema, sample: list(leaks))
    deleted = []
    monkeypatch.setattr(cli, "delete_branch", lambda branch_id: deleted.append(branch_id))
    return deleted


def test_success_keeps_branch_and_prints_url(monkeypatch, capsys):
    deleted = _patch(monkeypatch)
    assert cli.main([]) == 0
    assert deleted == []
    out = capsys.readouterr().out.strip().splitlines()
    assert "postgresql://masked" in "\n".join(out)
    payload = json.loads(out[-1])
    assert payload["branch"]["deleted"] is False
    assert payload["leaks"] == []


def test_delete_flag_discards_after_verify(monkeypatch):
    deleted = _patch(monkeypatch)
    assert cli.main(["--delete"]) == 0
    assert deleted == ["br_1"]


def test_leaks_delete_branch_and_exit_1(monkeypatch, capsys):
    deleted = _patch(monkeypatch, leaks=[Leak("customers", "notes", "email", 37, "Pre***")])
    assert cli.main([]) == 1
    assert deleted == ["br_1"]
    out = capsys.readouterr().out
    assert "customers.notes" in out and "postgresql://masked" not in out


def test_failure_mid_mask_deletes_and_exits_2(monkeypatch, capsys):
    deleted = _patch(monkeypatch, apply_error=RuntimeError("null value violates not-null"))
    with pytest.raises(SystemExit) as e:
        cli.main([])
    assert e.value.code == 2
    assert deleted == ["br_1"]
    assert "not-null" in capsys.readouterr().err


def test_bad_spec_exits_2_without_forking(monkeypatch, tmp_path, capsys):
    _patch(monkeypatch)
    monkeypatch.setattr(cli, "create_branch", lambda **kw: pytest.fail("must not fork"))
    bad = tmp_path / "m.yaml"
    bad.write_text("schema: s\n")
    with pytest.raises(SystemExit) as e:
        cli.main(["--mask", str(bad)])
    assert e.value.code == 2
