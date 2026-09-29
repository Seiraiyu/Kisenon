import json
import subprocess

import kisenon_preview as kp
import pytest

URL = "postgresql://app:s3cret@ep-1.kisenon.com:5432/main?sslmode=require"


class FakeKeon:
    """Records keon argv and answers from a small fake project."""

    def __init__(self, branches: dict[str, str]):
        self.branches = branches
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kw):
        if argv[0] == "psql":
            return subprocess.CompletedProcess(argv, 0, "1\n", "")
        args = argv[1:]
        self.calls.append(args)
        out = ""
        if args[:2] == ["branches", "list"]:
            out = json.dumps({"branches": [{"id": i, "name": n}
                                           for n, i in self.branches.items()]})
        elif args[:2] == ["branches", "create"]:
            out = json.dumps({"branch": {"id": "br_new", "name": args[args.index("--name") + 1]}})
        elif args[0] == "connection-string":
            out = json.dumps({"connection_string": URL})
        elif args[:2] == ["branches", "schema-diff"]:
            out = json.dumps({"diff": "+ALTER TABLE todos ADD due_date date"})
        return subprocess.CompletedProcess(argv, 0, out, "")


@pytest.fixture
def project(monkeypatch):
    monkeypatch.setenv("KISENON_PROJECT_ID", "proj_1")
    monkeypatch.delenv("GITHUB_ENV", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def test_redact_hides_password():
    assert kp.redact(URL) == "postgresql://app:****@ep-1.kisenon.com:5432/main?sslmode=require"
    assert "s3cret" not in kp.redact(URL)


def test_up_creates_branch_when_missing(project, monkeypatch, capsys):
    fake = FakeKeon({"main": "br_main"})
    monkeypatch.setattr(subprocess, "run", fake)
    assert kp.main(["up", "--pr", "7"]) == 0
    create = next(c for c in fake.calls if c[:2] == ["branches", "create"])
    assert create[create.index("--name") + 1] == "pr-7"
    assert "--wait" in create
    assert capsys.readouterr().out.strip() == URL


def test_up_resets_existing_branch(project, monkeypatch):
    fake = FakeKeon({"main": "br_main", "pr-7": "br_pr7"})
    monkeypatch.setattr(subprocess, "run", fake)
    assert kp.main(["up", "--pr", "7"]) == 0
    assert ["branches", "reset", "br_pr7", "-o", "json"] in fake.calls
    assert not any(c[:2] == ["branches", "create"] for c in fake.calls)


def test_up_in_actions_masks_and_writes_github_env(project, monkeypatch, tmp_path, capsys):
    env_file = tmp_path / "github_env"
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(subprocess, "run", FakeKeon({"main": "br_main"}))
    assert kp.main(["up", "--pr", "7"]) == 0
    out = capsys.readouterr().out
    assert "::add-mask::s3cret" in out
    assert out.replace("::add-mask::s3cret", "").replace(f"::add-mask::{URL}", "").strip() == ""
    assert env_file.read_text() == f"DATABASE_URL={URL}\n"


def test_comment_renders_results_diff_and_redacted_url(project, monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", FakeKeon({"main": "br_main", "pr-7": "br_pr7"}))
    out = tmp_path / "c.md"
    assert kp.main(["comment", "--pr", "7", "--migrations", "success",
                    "--tests", "failure", "--out", str(out)]) == 0
    body = out.read_text()
    assert "| Migrations | success |" in body
    assert "| Tests | failure |" in body
    assert "ADD due_date" in body
    assert "s3cret" not in body
    assert "app:****@ep-1.kisenon.com" in body


def test_comment_survives_schema_diff_failure(project, monkeypatch, tmp_path):
    fake = FakeKeon({"main": "br_main", "pr-7": "br_pr7"})

    def failing(argv, **kw):
        if argv[1:3] == ["branches", "schema-diff"]:
            return subprocess.CompletedProcess(argv, 1, "", "no_running_rw_endpoint")
        return fake(argv, **kw)
    monkeypatch.setattr(subprocess, "run", failing)
    out = tmp_path / "c.md"
    assert kp.main(["comment", "--pr", "7", "--out", str(out)]) == 0
    assert "schema diff unavailable" in out.read_text()


def test_render_comment_truncates_huge_diff():
    body = kp.render_comment(name="pr-1", migrations="success", tests="success",
                             diff="x" * (kp.MAX_DIFF_CHARS + 10), url=URL)
    assert "(truncated)" in body
    assert len(body) < 65_536


def test_down_deletes_with_cascade(project, monkeypatch):
    fake = FakeKeon({"main": "br_main", "pr-7": "br_pr7"})
    monkeypatch.setattr(subprocess, "run", fake)
    assert kp.main(["down", "--pr", "7"]) == 0
    assert ["branches", "delete", "--cascade", "br_pr7"] in fake.calls


def test_down_is_noop_when_branch_gone(project, monkeypatch):
    fake = FakeKeon({"main": "br_main"})
    monkeypatch.setattr(subprocess, "run", fake)
    assert kp.main(["down", "--pr", "7"]) == 0
    assert not any(c[:2] == ["branches", "delete"] for c in fake.calls)


def test_missing_project_exits_2(monkeypatch):
    monkeypatch.delenv("KISENON_PROJECT_ID", raising=False)
    assert kp.main(["down", "--pr", "7"]) == 2


def test_keon_missing_exits_2(project, monkeypatch):
    def missing(argv, **kw):
        raise FileNotFoundError("keon")
    monkeypatch.setattr(subprocess, "run", missing)
    assert kp.main(["down", "--pr", "7"]) == 2


def test_keon_failure_exits_1(project, monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", "denied"))
    assert kp.main(["down", "--pr", "7"]) == 1
