"""How the editor reads a finished claude call, and how it reports a missing CLI.

Only a failed call is searched for the backend's error phrases, so a rewrite of
a document that talks about rate limits comes back as the rewrite. An old CLI
that rejects one of the flags gets an error that says to upgrade. No test here
starts a process.
"""
import os
import subprocess

import pytest

from articulate import claude_cli, editor

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_claude_call")


class _Runner:
    def __init__(self, raises):
        self.raises = raises

    def __call__(self, *args, **kwargs):
        raise self.raises


@pytest.fixture()
def work():
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    import shutil
    shutil.rmtree(_TMP, ignore_errors=True)


def _completed(returncode, stdout="", stderr=""):
    return subprocess.CompletedProcess(["claude"], returncode, stdout, stderr)


def test_a_finished_rewrite_that_mentions_a_backend_error_comes_back(monkeypatch):
    # A document about rate limits is not a rate limit. Only a failed call is
    # searched for the backend's error phrases.
    text = "The API returns 429 at the rate limit, or when the credit balance is too low."
    monkeypatch.setattr(claude_cli, "run", lambda *a, **k: _completed(0, text + "\n"))
    assert editor.claude_call("instructions", "doc") == text


def test_a_failed_call_with_a_backend_error_is_a_closed_error(monkeypatch):
    # The CLI 2.1.251 prints a credit error on stdout and exits 1.
    monkeypatch.setattr(claude_cli, "run",
                        lambda *a, **k: _completed(1, "Credit balance is too low\n"))
    with pytest.raises(editor.ClaudeUnavailable) as info:
        editor.claude_call("instructions", "doc")
    assert "credit" in str(info.value)


def test_a_failed_call_with_output_is_still_a_failure(monkeypatch):
    monkeypatch.setattr(claude_cli, "run", lambda *a, **k: _completed(1, "API Error: 500\n"))
    with pytest.raises(RuntimeError) as info:
        editor.claude_call("instructions", "doc")
    assert not isinstance(info.value, editor.ClaudeUnavailable)
    assert "500" in str(info.value)


def test_an_old_cli_that_rejects_a_flag_is_told_to_upgrade(monkeypatch):
    err = "error: unknown option '--setting-sources'\n"
    monkeypatch.setattr(claude_cli, "run", lambda *a, **k: _completed(1, "", err))
    with pytest.raises(editor.ClaudeUnavailable) as info:
        editor.claude_call("instructions", "doc")
    msg = str(info.value)
    assert "upgrade" in msg.lower() and claude_cli.TESTED_CLI_VERSION in msg


def test_editor_reports_a_missing_cli_through_its_closed_error(monkeypatch, capsys, work):
    from articulate import backends
    monkeypatch.delenv(claude_cli.ENV_VAR, raising=False)
    monkeypatch.setenv("PATH", "")
    assert editor.ClaudeUnavailable is claude_cli.ClaudeUnavailable
    monkeypatch.setattr(claude_cli.subprocess, "Popen", _Runner(raises=AssertionError("started")))
    with pytest.raises(editor.ClaudeUnavailable) as info:
        editor.claude_call("instructions", "text")
    assert claude_cli.ENV_VAR in str(info.value)
    # The public editor now falls back; stub selection to keep the test offline.
    reason = str(info.value)
    monkeypatch.setattr(backends, "complete", lambda *a, **k: (
        "", backends.BackendInfo(backend="none", model=None,
                                 attempts=[{"backend": "claude-cli", "reason": reason}])))
    doc = os.path.join(work, "d.md")
    with open(doc, "w", encoding="utf-8") as fh:
        fh.write("Some prose.\n")
    editor.judge(doc)
    out = capsys.readouterr().out
    assert "model layer unavailable" in out and claude_cli.ENV_VAR in out


def test_the_old_editor_hooks_are_gone():
    # editor.CLAUDE and editor.run no longer steer the model call. Keeping either
    # would let a caller patch it and still reach the real CLI.
    assert not hasattr(editor, "CLAUDE")
    assert not hasattr(editor, "run")
