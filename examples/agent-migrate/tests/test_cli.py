import pytest

from agent_migrate.cli import build_parser, main


def test_parser_requires_request():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["ask"])


def test_parser_defaults():
    args = build_parser().parse_args(["ask", "--request", "add status"])
    assert args.provider == "anthropic"
    assert args.parent == "main"
    assert args.max_attempts == 5
    assert args.auto_promote is False


def test_main_errors_without_project(monkeypatch, capsys):
    monkeypatch.delenv("KISENON_PROJECT_ID", raising=False)
    monkeypatch.setattr("sys.argv", ["agent-migrate", "ask", "--request", "x"])
    monkeypatch.setattr("agent_migrate.cli.load_dotenv", lambda *a, **k: None)
    with pytest.raises(SystemExit) as ei:
        main()
    assert ei.value.code == 2
    assert "KISENON_PROJECT_ID" in capsys.readouterr().err


def test_main_errors_without_kisenon_url(monkeypatch, capsys):
    monkeypatch.setenv("KISENON_PROJECT_ID", "p")
    monkeypatch.delenv("KISENON_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["agent-migrate", "ask", "--request", "x"])
    monkeypatch.setattr("agent_migrate.cli.load_dotenv", lambda *a, **k: None)
    with pytest.raises(SystemExit) as ei:
        main()
    assert ei.value.code == 2
    assert "KISENON_URL" in capsys.readouterr().err


def test_main_errors_without_provider_key(monkeypatch, capsys):
    monkeypatch.setenv("KISENON_PROJECT_ID", "p")
    monkeypatch.setenv("KISENON_URL", "postgresql://x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["agent-migrate", "ask", "--request", "x"])
    monkeypatch.setattr("agent_migrate.cli.load_dotenv", lambda *a, **k: None)
    with pytest.raises(SystemExit) as ei:
        main()
    assert ei.value.code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
