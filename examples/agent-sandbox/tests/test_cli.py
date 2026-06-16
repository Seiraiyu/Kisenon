import pytest

from agent_sandbox.cli import build_parser, generate_branch_name


def test_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_minimal():
    args = build_parser().parse_args(["ask", "--question", "hi"])
    assert args.question == "hi"
    assert args.provider == "anthropic"
    assert args.model is None
    assert args.max_queries == 10
    assert args.max_wall_s == 120
    assert args.row_cap == 1000


def test_parser_all_flags():
    args = build_parser().parse_args([
        "ask",
        "--question", "go",
        "--provider", "openai",
        "--model", "gpt-5.1",
        "--max-queries", "3",
        "--max-wall-s", "30",
        "--row-cap", "50",
        "--pretty",
        "--always-delete",
        "--project", "proj_42",
        "--name", "x",
    ])
    assert args.provider == "openai"
    assert args.model == "gpt-5.1"
    assert args.max_queries == 3
    assert args.pretty is True
    assert args.always_delete is True
    assert args.project == "proj_42"
    assert args.name == "x"


def test_generate_branch_name_is_unique_and_well_formed():
    a = generate_branch_name()
    b = generate_branch_name()
    assert a != b
    assert a.startswith("agent-sandbox-")
    assert len(a) < 64
    assert all(c.isalnum() or c == "-" for c in a)
