import os

from harness.oracle import run_env, ENV_ALLOWLIST


def test_a_secret_in_the_parent_environment_does_not_reach_the_child(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_SIGNING_KEY", "s3cret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-do-not-leak")
    env = run_env()
    assert "FLYWHEEL_SIGNING_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "s3cret" not in "".join(env.values())


def test_the_interpreter_still_works(monkeypatch):
    # PATH and the platform loader variables must survive or pytest cannot run.
    env = run_env()
    assert "PATH" in env
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    if os.name == "nt":
        assert "SYSTEMROOT" in env


def test_allowlist_is_deny_by_default(monkeypatch):
    monkeypatch.setenv("SOME_FUTURE_VARIABLE_NOBODY_ANTICIPATED", "x")
    assert "SOME_FUTURE_VARIABLE_NOBODY_ANTICIPATED" not in run_env()
    assert "SOME_FUTURE_VARIABLE_NOBODY_ANTICIPATED" not in ENV_ALLOWLIST


def test_caller_can_add_explicit_extras():
    env = run_env({"FLYWHEEL_TASK_ID": "t1"})
    assert env["FLYWHEEL_TASK_ID"] == "t1"
