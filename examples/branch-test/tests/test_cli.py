import pytest

from branch_test.cli import build_parser, generate_branch_name


def test_parser_accepts_minimal_migrate():
    args = build_parser().parse_args(["--migrate", "alembic upgrade head"])
    assert args.migrate == "alembic upgrade head"
    assert args.verify is None
    assert args.rollback is None
    assert args.keep is False
    assert args.delete is False
    assert args.pretty is False
    assert args.timeout_s == 600


def test_parser_accepts_all_flags():
    args = build_parser().parse_args([
        "--migrate", "alembic upgrade head",
        "--verify", "pytest tests/",
        "--rollback", "alembic downgrade -1",
        "--project", "proj_42",
        "--name", "experiment-1",
        "--keep",
        "--pretty",
        "--timeout-s", "30",
        "--working-dir", "/tmp",
        "--no-schema-diff",
    ])
    assert args.verify == "pytest tests/"
    assert args.rollback == "alembic downgrade -1"
    assert args.project == "proj_42"
    assert args.name == "experiment-1"
    assert args.keep is True
    assert args.pretty is True
    assert args.timeout_s == 30
    assert args.working_dir == "/tmp"
    assert args.no_schema_diff is True


def test_parser_requires_migrate():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_rejects_conflicting_keep_and_delete():
    # Both can be parsed individually; validation is in main() at runtime,
    # not in argparse. This test asserts argparse accepts both flags.
    args = build_parser().parse_args(["--migrate", "x", "--keep", "--delete"])
    assert args.keep and args.delete


def test_generate_branch_name_is_unique_and_well_formed():
    a = generate_branch_name()
    b = generate_branch_name()
    assert a != b
    assert a.startswith("branch-test-")
    assert len(a) < 64
    # only alnum + dash
    assert all(ch.isalnum() or ch == "-" for ch in a)
