"""I3 and I18, continued: environment redirection, worktree homes, the Codex
output shape, canary leakage, and FLYWHEEL_CAPTURE=off."""
import json
import logging
import os

import pytest

from capture_channel_fixture import (RecordingListener, all_bytes_under, hook_env,
                                     prompt_event, run_hook, running_gateway,
                                     spool_files, stop_event)

CANARY_PROMPT = "CANARY-PROMPT-" + "x7" * 6
CANARY_ANSWER = "CANARY-ANSWER-" + "k3" * 6


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "home"
    path.mkdir()
    return path


@pytest.fixture
def work(tmp_path):
    path = tmp_path / "work"
    path.mkdir()
    return path


def _receipts(home):
    from harness.store import query_entities
    return query_entities(kind="turn-receipt", home=home)


def test_redirect_variables_change_nothing(home, work, monkeypatch):
    env = hook_env({"FLYWHEEL_GATEWAY_URL": "http://127.0.0.1:9",
                    "FLYWHEEL_CAPTURE_ALLOW_REMOTE": "1"})
    with running_gateway(home, monkeypatch):
        proc = run_hook(home, "stop", stop_event(), cwd=work, env=env)
    assert proc.returncode == 0, proc.stderr.decode()
    assert len(_receipts(home)) == 1


def test_a_mismatched_flywheel_home_is_refused_and_spooled_to_the_resolved_home(
        home, work, tmp_path, monkeypatch):
    other = tmp_path / "elsewhere"
    other.mkdir()
    with running_gateway(home, monkeypatch):
        proc = run_hook(home, "stop", stop_event(), cwd=work,
                        env=hook_env({"FLYWHEEL_HOME": str(other)}))
    assert proc.returncode == 1 and "HOME_MISMATCH" in proc.stderr.decode()
    assert _receipts(home) == []
    assert len(spool_files(home)) == 1
    assert not (other / "state").exists()


def test_a_matching_flywheel_home_is_accepted(home, work, monkeypatch):
    with running_gateway(home, monkeypatch):
        proc = run_hook(home, "stop", stop_event(), cwd=work,
                        env=hook_env({"FLYWHEEL_HOME": str(home)}))
    assert proc.returncode == 0, proc.stderr.decode()


def test_a_home_inside_a_git_work_tree_is_refused_without_a_spool(tmp_path, work):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    home = repo / "nested" / "home"
    home.mkdir(parents=True)
    proc = run_hook(home, "stop", stop_event(), cwd=work)
    assert proc.returncode == 1 and "HOME_IN_WORKTREE" in proc.stderr.decode()
    assert not (home / "state").exists()


def test_a_git_file_pointing_at_a_gitdir_also_marks_a_work_tree(tmp_path):
    from harness.capture_hooks.home import in_git_worktree
    (tmp_path / "wt").mkdir()
    (tmp_path / "wt" / ".git").write_text("gitdir: ../elsewhere/.git/worktrees/wt\n")
    assert in_git_worktree(tmp_path / "wt" / "home")


def test_a_stray_git_folder_without_head_is_not_a_work_tree(tmp_path):
    from harness.capture_hooks.home import in_git_worktree
    (tmp_path / "stray" / ".git" / "info").mkdir(parents=True)
    assert not in_git_worktree(tmp_path / "stray" / "home")


def test_a_home_inside_the_working_directory_is_refused(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    proc = run_hook(home, "stop", stop_event(), cwd=tmp_path)
    assert "HOME_IN_WORKTREE" in proc.stderr.decode()


def test_the_codex_shape_exits_zero_with_a_system_message(home, work):
    proc = run_hook(home, "stop", stop_event(turn_id="turn-1"), client="codex", cwd=work)
    assert proc.returncode == 0
    message = json.loads(proc.stdout)["systemMessage"]
    assert "TOKEN_MISSING" in message and "flywheel traces doctor" in message
    assert len(spool_files(home)) == 1


def test_the_claude_prompt_shape_exits_zero_with_a_system_message(home, work):
    proc = run_hook(home, "prompt", prompt_event(), cwd=work)
    assert proc.returncode == 0
    assert "TOKEN_MISSING" in json.loads(proc.stdout)["systemMessage"]


def test_unacknowledged_failures_are_counted_at_the_next_prompt(home, work, monkeypatch):
    run_hook(home, "stop", stop_event(), cwd=work)
    run_hook(home, "stop", stop_event(), cwd=work)
    with running_gateway(home, monkeypatch):
        proc = run_hook(home, "prompt", prompt_event(), cwd=work)
    assert proc.returncode == 0
    message = json.loads(proc.stdout)["systemMessage"]
    assert "2 captures failed" in message and "flywheel traces doctor" in message


def test_no_canary_or_token_reaches_output_spool_or_logs(home, work, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    event = stop_event(answer=CANARY_ANSWER, prompt=CANARY_PROMPT)
    with running_gateway(home, monkeypatch):
        token = (home / "gateway.token").read_text().strip()
        ok = run_hook(home, "stop", event, cwd=work)
        ok_prompt = run_hook(home, "prompt", prompt_event(CANARY_PROMPT), cwd=work)
    (home / "gateway.endpoint").unlink(missing_ok=True)
    failed = run_hook(home, "stop", event, cwd=work)
    assert ok.returncode == 0 and failed.returncode == 1
    streams = b"".join(p.stdout + p.stderr for p in (ok, ok_prompt, failed))
    spooled = all_bytes_under(home / "state" / "capture-failures")
    logs = "\n".join(r.getMessage() for r in caplog.records).encode()
    for blob in (streams, spooled, logs):
        for secret in (CANARY_PROMPT.encode(), CANARY_ANSWER.encode(), token.encode()):
            assert secret not in blob


def _off_env():
    return hook_env({"FLYWHEEL_CAPTURE": "off"})


def test_capture_off_sends_nothing_notices_once_per_session_and_counts(home, work):
    from harness.capture_hooks import spool
    from harness.gateway_endpoint_file import write_endpoint
    (home / "gateway.token").write_text("synthetic-token-value")
    listener = RecordingListener(lambda data: b"{}")
    try:
        write_endpoint(home, "127.0.0.1", listener.port, os.getpid())
        first = run_hook(home, "stop", stop_event(), cwd=work, env=_off_env())
        second = run_hook(home, "prompt", prompt_event(), cwd=work, env=_off_env())
        other = run_hook(home, "stop", stop_event(session="1" * 8 + "-2222-3333-4444-"
                                                   + "5" * 12), cwd=work, env=_off_env())
    finally:
        listener.close()
    assert listener.received == []
    assert first.returncode == 0 and other.returncode == 0
    notice = json.loads(first.stdout)["systemMessage"]
    assert "FLYWHEEL_CAPTURE=off" in notice and str(work) in notice
    assert second.returncode == 0 and second.stdout.strip() in (b"", b"{}")
    assert json.loads(other.stdout)["systemMessage"]
    assert spool.suppression_count(home) == 3
    assert spool_files(home) == []
    stored = all_bytes_under(home / "state")
    assert str(work).encode() not in stored
    assert str(work).encode("utf-16-le") not in stored
