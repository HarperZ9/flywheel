"""I15: destructive custody events also go to an append-only witness outside
Flywheel's files (the Windows Application log), and the doctor names a ledger
entry whose event is missing. Other systems report "no witness"."""
import secrets
import sys

import pytest

from harness import trace_witness
from harness.trace_custody_ledger import CustodyLedger
from harness.trace_witness import MemorySink, record_custody_event, reconcile

OWNER = "owner_" + "a" * 32


@pytest.fixture
def home(tmp_path):
    (tmp_path / "state").mkdir()
    return tmp_path


def test_a_recorded_event_matches_its_ledger_entry(home):
    sink = MemorySink()
    record_custody_event(home, OWNER, "deletion", {"plan_digest": "a" * 64, "items": 2},
                         "none", sink=sink)
    entries = CustodyLedger(home, OWNER).entries()
    assert reconcile(entries, sink.read()) == []


def test_a_dropped_event_is_a_witness_mismatch(home):
    sink = MemorySink(drop_next=True)
    record_custody_event(home, OWNER, "export", {"root_digest": "b" * 64, "items": 1},
                         "none", sink=sink)
    mismatches = reconcile(CustodyLedger(home, OWNER).entries(), sink.read())
    assert [m["code"] for m in mismatches] == ["WITNESS_MISMATCH"]
    assert mismatches[0]["kind"] == "export"


def test_only_witnessed_kinds_need_an_event(home):
    sink = MemorySink()
    CustodyLedger(home, OWNER).append("capture_count", {"client": "codex", "turns": 1})
    assert reconcile(CustodyLedger(home, OWNER).entries(), sink.read()) == []


def test_the_event_text_holds_counts_and_digests_and_no_content(home):
    sink = MemorySink()
    record_custody_event(home, OWNER, "deletion",
                         {"plan_digest": "c" * 64, "items": 4, "stores": ["S1"]},
                         "windows-hello", sink=sink)
    text = sink.texts[-1]
    assert "kind=deletion" in text and "presence=windows-hello" in text
    assert "plan=" + "c" * 16 in text and "seq=0" in text
    assert "\\" not in text and "/" not in text


@pytest.mark.skipif(sys.platform == "win32", reason="the Windows sink is real there")
def test_other_systems_say_there_is_no_witness():
    assert trace_witness.default_sink().status() == "no witness on this system"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Application log")
def test_a_planted_delete_reaches_the_application_log_and_reads_back(home):
    digest = secrets.token_hex(32)
    sink = trace_witness.default_sink()
    record_custody_event(home, OWNER, "deletion", {"plan_digest": digest, "items": 1},
                         "none", sink=sink)
    found = [e for e in sink.read() if e.get("plan") == digest[:16]]
    assert len(found) == 1
    assert found[0]["kind"] == "deletion" and found[0]["presence"] == "none"
    assert set(found[0]) <= {"kind", "seq", "plan", "presence", "items", "owner"}
