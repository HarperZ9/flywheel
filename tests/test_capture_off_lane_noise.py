"""Capture-off events from lane processes stay one ledger line per lane and
leave no files behind; an owner's own opt-out keeps its notice and record.

Correctness review F1 of 1.1.0: every lane child runs with capture off, and
articulate runs each ``claude -p`` in a fresh private folder under its lane
folder with the owner's user hooks loaded. Each call then left two
suppression records and a session marker in the spool (never removed), one
``capture_suppressed`` ledger entry and one event-log witness per call folder,
and a doctor line naming temp folders the owner never used. The count exists
so an owner notices capture was turned off; lane noise buried that.
"""
from __future__ import annotations

import json

import pytest

from delete_fixtures import OWNER
from harness.capture_hooks import __main__ as hook, spool
from harness.trace_capture_off import record_suppressions
from harness.trace_custody_ledger import CustodyLedger
from harness.trace_doctor_checks import failures_check
from harness.trace_witness import MemorySink


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    (home / "state").mkdir(parents=True)
    (home / "owner.ref").write_text(OWNER)
    return home


def _event(kind, session):
    doc = {"session_id": session, "hook_event_name": "Stop" if kind == "stop"
           else "UserPromptSubmit"}
    doc.update({"last_assistant_message": "x"} if kind == "stop" else {"prompt": "x"})
    return json.dumps(doc).encode()


def _call(home, cwd, session):
    """One articulate-shaped claude -p call: a prompt and a stop event."""
    outs = []
    for kind in ("prompt", "stop"):
        code, out, err = hook.run([kind, "--client", "claude-code", "--home", str(home)],
                                  _event(kind, session), {"FLYWHEEL_CAPTURE": "off"}, str(cwd))
        assert code == 0, err
        outs.append(out)
    return outs


def _suppressed_entries(home):
    return [e["fields"] for e in CustodyLedger(home, OWNER).entries()
            if e["kind"] == "capture_suppressed"]


def test_many_lane_calls_fold_into_one_entry_per_lane_and_leave_no_files(home):
    for i in range(4):
        cwd = home / "lanes" / "articulate" / "tmp" / f"call{i}" / "cwd"
        cwd.mkdir(parents=True)
        outs = _call(home, cwd, f"0f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a{i:02d}")
        assert not any("capture is off" in out.lower() for out in outs), outs
    sink = MemorySink()
    assert record_suppressions(home, OWNER, sink=sink) == 8
    assert _suppressed_entries(home) == [
        {"client": "claude-code", "project_ref": "lane:articulate", "count": 8}]
    assert len(sink.read()) == 1
    left = [p.name for p in (spool.spool_dir(home) / "suppressed").iterdir()
            if p.name != ".ledgered"]
    assert left == []
    state, detail, _ = failures_check(home, ack=False)
    assert "tmp" not in detail and "call0" not in detail


def test_control_an_owner_opt_out_keeps_its_notice_record_and_project(home, tmp_path):
    work = tmp_path / "project"
    work.mkdir()
    outs = _call(home, work, "0f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a99")
    assert any("capture is off" in out.lower() for out in outs), outs
    assert record_suppressions(home, OWNER, sink=MemorySink()) == 2
    (entry,) = _suppressed_entries(home)
    assert entry["count"] == 2 and not entry["project_ref"].startswith("lane:")
    assert len(spool.suppressions(home)) == 2          # kept for the doctor
