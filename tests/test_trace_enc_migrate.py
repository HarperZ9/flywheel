"""FW-04b: legacy plaintext traces are encrypted from the last file
backwards, so every intermediate state satisfies the prefix rule and reads; a
trace whose writer holds its lock is skipped; the report names the freed
clusters the plaintext leaves behind."""
import pytest

from harness import trace_enc_migrate
from harness.gateway_agent_trace import AgentTrace
from harness.trace_enc import NoProvider
from harness.trace_enc_migrate import migrate_legacy
from trace_enc_fakes import StreamTestProvider, using

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "b" * 32
OPERATION = "op_" + "c" * 32


class Fault(Exception):
    pass


@pytest.fixture
def legacy(tmp_path):
    with using(NoProvider()):
        trace = AgentTrace(tmp_path, OWNER, JOURNEY, OPERATION)
        for index in range(3):
            trace.append("progress", {"index": index})
    return tmp_path


def _files(state):
    return {p.name: p.read_bytes() for p in state.rglob("*.json")
            if "gateway-agent-traces" in p.parts}


def _read(state):
    return [r["payload"]["index"] for r in AgentTrace(state, OWNER, JOURNEY, OPERATION).read()]


def test_files_convert_from_the_last_backwards_and_the_trace_still_reads(legacy):
    order = []
    with using(StreamTestProvider()):
        report = migrate_legacy(legacy, on_file=order.append)
        assert _read(legacy) == [0, 1, 2]
    assert order == ["head-00000002.json", "00000002.json", "head-00000001.json",
                     "00000001.json", "head-00000000.json", "00000000.json"]
    assert all(raw.startswith(b"FWENC1\n") for raw in _files(legacy).values())
    assert report["converted_files"] == 6 and report["items"] == 1
    assert report["residue"] == {"freed_clusters": 6}


@pytest.mark.parametrize("after", range(6))
def test_a_fault_after_any_file_leaves_a_readable_trace_and_a_rerun_finishes(legacy, after):
    seen = []

    def fault(name):
        seen.append(name)
        if len(seen) == after + 1:
            raise Fault(name)
    with using(StreamTestProvider()):
        with pytest.raises(Fault):
            migrate_legacy(legacy, on_file=fault)
        assert _read(legacy) == [0, 1, 2]
        migrate_legacy(legacy)
        assert _read(legacy) == [0, 1, 2]
    assert all(raw.startswith(b"FWENC1\n") for raw in _files(legacy).values())


def test_a_trace_whose_writer_holds_its_lock_is_skipped(legacy):
    before = _files(legacy)
    trace = AgentTrace(legacy, OWNER, JOURNEY, OPERATION)
    with using(StreamTestProvider()):
        with trace.hold():
            report = migrate_legacy(legacy)
    assert report["skipped"] == {"LOCKED": 1} and report["converted_files"] == 0
    assert _files(legacy) == before


def test_an_already_encrypted_trace_is_left_alone(legacy):
    with using(StreamTestProvider()):
        migrate_legacy(legacy)
        again = migrate_legacy(legacy)
    assert again["converted_files"] == 0 and again["items"] == 0


def test_without_an_os_key_store_nothing_is_converted(legacy):
    with using(NoProvider()):
        report = migrate_legacy(legacy)
    assert report["state"] == "UNAVAILABLE" and report["converted_files"] == 0


def test_the_cli_prints_the_report(legacy, capsys, monkeypatch):
    from harness import trace_cli
    monkeypatch.setenv("FLYWHEEL_HOME", str(legacy.parent))
    monkeypatch.setattr(trace_enc_migrate, "_state_root", lambda: legacy)
    with using(StreamTestProvider()):
        assert trace_cli.main(["encrypt", "--legacy"]) == 0
    out = capsys.readouterr().out
    assert "6 files encrypted in 1 trace" in out and "freed clusters" in out


def test_encrypting_keeps_the_record_times_retention_reads(legacy):
    """C6: a trace 90 days old still reads 90 days old after migration."""
    import os
    import time
    stamp = time.time() - 90 * 86400
    for path in legacy.rglob("*.json"):
        os.utime(path, (stamp, stamp))
    with using(StreamTestProvider()):
        migrate_legacy(legacy)
    for path in legacy.rglob("*.json"):
        assert abs(path.stat().st_mtime - stamp) < 2, path.name


def test_one_unreadable_trace_does_not_stop_the_others(legacy):
    """C7: a corrupt legacy trace is skipped as UNREADABLE; the rest convert."""
    with using(NoProvider()):
        other = AgentTrace(legacy, OWNER, JOURNEY, "op_" + "d" * 32)
        other.append("progress", {"index": 9})
    broken = next(p for p in legacy.rglob("head-00000001.json") if OPERATION in str(p))
    broken.write_bytes(b"{not json")
    with using(StreamTestProvider()):
        report = migrate_legacy(legacy)
    assert report["skipped"] == {"UNREADABLE": 1}
    assert report["items"] == 1
    assert "cannot be read" in " ".join(trace_enc_migrate.render(report))
