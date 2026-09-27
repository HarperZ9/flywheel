"""7.6 continuous capture: with the transcript archive in effect, the
SessionEnd hook asks the gateway to import the ended session by id; with the
gateway down, a spool record names client and session id, and
`flywheel traces import --pending` imports it later."""
import json
import time

import pytest

from capture_channel_fixture import hook_env, run_hook, running_gateway
from import_fixtures import OWNER, SESSION, claude_tree
from trace_enc_fakes import StreamTestProvider, using


def _archive_on(home):
    from harness.trace_capture_settings import adopt, digest, write_file
    from harness.trace_presence import confirm
    from harness.trace_witness import MemorySink
    settings = write_file(home, {"archive_transcripts": "on"})
    adopt(home, OWNER, confirm(home / "state", OWNER, "capture_settings", digest(settings),
                               "archive on"), sink=MemorySink())


def _event():
    return {"session_id": SESSION, "hook_event_name": "SessionEnd", "reason": "exit"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from harness import trace_import_session
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    (home / "owner.ref").write_text(OWNER)
    root, _, _ = claude_tree(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    monkeypatch.setattr(trace_import_session, "_LAST", {})
    with using(StreamTestProvider()):
        yield home, work, root


def _imported(home):
    from harness.trace_import_core import ImportStore
    return ImportStore(home, OWNER).item_refs()


def test_the_hook_asks_the_gateway_to_import_the_ended_session(setup, monkeypatch):
    home, work, root = setup
    with running_gateway(home, monkeypatch):
        _archive_on(home)
        proc = run_hook(home, "session-end", _event(), cwd=work,
                        env=hook_env({"CLAUDE_CONFIG_DIR": str(root)}))
        assert proc.returncode == 0, proc.stderr.decode()
        deadline = time.monotonic() + 20
        while not _imported(home) and time.monotonic() < deadline:
            time.sleep(0.05)
    assert len(_imported(home)) == 1


def test_with_the_archive_off_the_hook_sends_nothing(setup, monkeypatch):
    home, work, root = setup
    with running_gateway(home, monkeypatch):
        proc = run_hook(home, "session-end", _event(), cwd=work)
    assert proc.returncode == 0 and _imported(home) == []


def test_with_the_gateway_down_a_spool_record_allows_a_later_import(setup, monkeypatch, capsys):
    from harness import trace_cli
    home, work, root = setup
    (home / "gateway.token").write_text("synthetic-token-value")
    proc = run_hook(home, "session-end", _event(), cwd=work)
    assert proc.returncode == 1 and "GATEWAY_NOT_RUNNING" in proc.stderr.decode()
    records = [json.loads(p.read_text()) for p in
               (home / "state" / "capture-failures" / "v1").glob("f-*.json")]
    assert [(r["client"], r["event"], r["session_id"]) for r in records] == [
        ("claude-code", "session-end", SESSION)]
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    assert trace_cli.main(["import", "--pending"]) == 0
    assert "The transcript archive is off, so nothing was imported" in (
        capsys.readouterr().out)
    assert _imported(home) == []
    _archive_on(home)
    assert trace_cli.main(["import", "--pending"]) == 0
    assert "1 pending session imported" in capsys.readouterr().out
    assert len(_imported(home)) == 1
    assert list((home / "state" / "capture-failures" / "v1").glob("f-*.json")) == []


def test_a_pending_session_with_nothing_new_is_not_counted_as_imported(
        setup, monkeypatch, capsys):
    from harness import trace_cli, trace_import_session
    from harness.capture_hooks import spool
    home, work, root = setup
    monkeypatch.setenv("FLYWHEEL_HOME", str(home))
    _archive_on(home)
    assert spool.write_failure(home, "claude-code", "session-end", SESSION, None,
                               "GATEWAY_NOT_RUNNING")
    monkeypatch.setattr(trace_import_session, "import_session",
                        lambda *a, **k: {"imported": 0, "skipped": {"already": 1}})
    assert trace_cli.main(["import", "--pending"]) == 0
    out = capsys.readouterr().out
    assert "0 pending sessions imported" in out and "1 had nothing new" in out
