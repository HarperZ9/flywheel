"""Custody writes are durable: the temporary file is flushed to disk before
it replaces the record, and the folder is flushed after, so an unclean
shutdown cannot leave a zero-filled record where the old one was. Each
custody writer goes through the one helper."""
import os

import pytest

from delete_fixtures import OWNER, SESSION
from harness import trace_durable
from trace_enc_fakes import StreamTestProvider, using


def test_the_file_is_flushed_before_the_replace_and_the_folder_after(tmp_path, monkeypatch):
    events = []
    real_fsync, real_replace, real_dir = os.fsync, trace_durable.replace_through, \
        trace_durable.fsync_directory
    monkeypatch.setattr(os, "fsync", lambda fd: events.append("fsync") or real_fsync(fd))
    monkeypatch.setattr(trace_durable, "replace_through",
                        lambda a, b: events.append("replace") or real_replace(a, b))
    monkeypatch.setattr(trace_durable, "fsync_directory",
                        lambda d: events.append("dir") or real_dir(d))
    target = tmp_path / "record.enc"
    target.write_bytes(b"old")
    trace_durable.write_durable(target, b"new")
    assert target.read_bytes() == b"new"
    assert events == ["fsync", "replace", "dir"]
    assert not list(tmp_path.glob("*.tmp"))


def test_times_can_be_carried_over(tmp_path):
    target = tmp_path / "r"
    target.write_bytes(b"old")
    os.utime(target, ns=(1_000_000_000, 978_307_200_000_000_000))
    trace_durable.write_durable(target, b"new", times=os.stat(target))
    assert os.stat(target).st_mtime_ns == 978_307_200_000_000_000


@pytest.fixture
def commits(monkeypatch):
    seen = []
    real = trace_durable.commit
    monkeypatch.setattr(trace_durable, "commit", lambda t, p: seen.append(p.name) or real(t, p))
    return seen


def test_captured_turns_are_written_durably(tmp_path, commits):
    from harness.trace_turn_store import TurnStore
    with using(StreamTestProvider()):
        (tmp_path / "state").mkdir()
        TurnStore(tmp_path, OWNER).prompt("claude-code", SESSION, "pid-1", text="x")
    assert any(name.endswith(".enc") for name in commits)


def test_presence_records_are_written_durably(tmp_path, commits):
    from harness.trace_presence import confirm
    confirm(tmp_path / "state", OWNER, "delete_apply", "d" * 64, "delete")
    assert commits


def test_legacy_migration_writes_durably(tmp_path, commits):
    from harness.gateway_agent_trace import AgentTrace
    from harness.trace_enc import NoProvider
    from harness.trace_enc_migrate import migrate_legacy
    with using(NoProvider()):
        AgentTrace(tmp_path, OWNER, "jrn_" + "b" * 32, "op_" + "c" * 32).append(
            "progress", {"index": 0})
    with using(StreamTestProvider()):
        migrate_legacy(tmp_path)
    assert "00000000.json" in commits
