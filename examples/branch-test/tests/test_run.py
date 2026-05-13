import subprocess

from branch_test.run import (
    RunOptions,
    StepResult,
    run_step,
    wait_for_endpoint_ready,
)


def test_run_step_captures_exit_code_and_duration(monkeypatch):
    def fake_run(args, **kw):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="out\n", stderr="err\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    step = run_step(name="migrate", command="echo hi", env={"X": "1"}, cwd="/tmp", timeout_s=10)
    assert step.exit_code == 0
    assert step.duration_ms >= 0
    assert step.stdout_tail.strip() == "out"
    assert step.stderr_tail.strip() == "err"


def test_run_step_captures_non_zero_exit(monkeypatch):
    def fake_run(args, **kw):
        return subprocess.CompletedProcess(args=args, returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    step = run_step(name="migrate", command="false", env={}, cwd=".", timeout_s=10)
    assert step.exit_code == 2
    assert "boom" in step.stderr_tail


def test_run_step_truncates_long_output_with_flag(monkeypatch):
    big = "x" * 20_000

    def fake_run(args, **kw):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=big, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    step = run_step(name="migrate", command="dump", env={}, cwd=".", timeout_s=10)
    assert step.stdout_truncated is True
    assert len(step.stdout_tail) < len(big)


def test_run_step_handles_timeout(monkeypatch):
    def fake_run(args, **kw):
        raise subprocess.TimeoutExpired(cmd="sleep", timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    step = run_step(name="verify", command="sleep 99", env={}, cwd=".", timeout_s=1)
    assert step.exit_code == 124  # convention for timeout
    assert "timeout" in step.stderr_tail.lower()


def test_step_result_dataclass_shape():
    s = StepResult(
        name="migrate", command="echo hi",
        exit_code=0, duration_ms=42,
        stdout_tail="hi", stderr_tail="",
        stdout_truncated=False, stderr_truncated=False,
    )
    assert s.exit_code == 0


def test_run_options_defaults():
    opts = RunOptions(
        migrate_cmd="x", verify_cmd=None, rollback_cmd=None,
        working_dir=".", timeout_s=600,
    )
    assert opts.verify_cmd is None
    assert opts.rollback_cmd is None


def test_wait_for_endpoint_returns_true_on_first_success(monkeypatch):
    def fake_run(args, **kw):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="1\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert wait_for_endpoint_ready("postgresql://x", max_wait_s=1) is True


def test_wait_for_endpoint_returns_false_when_never_ready(monkeypatch):
    def fake_run(args, **kw):
        return subprocess.CompletedProcess(
            args=args, returncode=2, stdout="", stderr="endpoint not found"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    # max_wait_s=0 -> the while loop exits immediately; psql wasn't missing
    # so the fixed-sleep fallback doesn't fire.
    assert wait_for_endpoint_ready("postgresql://x", max_wait_s=0) is False


def test_wait_for_endpoint_falls_back_when_psql_missing(monkeypatch):
    def fake_run(args, **kw):
        raise FileNotFoundError("psql")

    sleeps: list[float] = []
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("branch_test.run.time.sleep", lambda s: sleeps.append(s))
    assert wait_for_endpoint_ready("postgresql://x", max_wait_s=1) is True
    assert sleeps  # the fixed-sleep fallback fired
