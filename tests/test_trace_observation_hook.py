"""Shared receipt and escalation path: observation receipts and trace flags in the monitor chain."""
import json
from pathlib import Path

import pytest

from harness.preaction import trace_flag
from harness.preaction.contract import ALLOW, HOLD, ProposedCall, RunContext
from harness.preaction.core import Monitor
from harness.preaction.escalate import Escalator
from harness.preaction.verify import verify_store
from harness.trace_observation import monitor_hook
from harness.trace_observation.observe import observe_run, render_report
from harness.trace_observation.receipt import FloatInReceipt, ObservationLedger, build_receipt

FIX = Path(__file__).parent / "fixtures" / "trace_observation"
CLOCK = lambda: "2026-10-01T12:00:00Z"  # noqa: E731


def turn(name):
    f = json.loads((FIX / name).read_text(encoding="utf-8"))
    return {"request": f["request"], "response": f["response"]}


def ctx(tmp_path):
    return RunContext(run_id="run-1", workspace=str(tmp_path / "ws"), goal="fix the bug")


def read_call(tmp_path):
    return ProposedCall(tool="read_file", args={"path": str(tmp_path / "ws" / "a.py")}, seq=1,
                        tool_use_id="t1")


def test_clean_run_writes_receipts_and_raises_no_hold(tmp_path):
    home = tmp_path / "mon"
    res = observe_run(home, run_id="run-1", provider="anthropic",
                      turns=[turn("anthropic_summarized.json")], observed_on="2026-10-01")
    assert res["holds"] == [] and all(c["passed"] == "true" for c in res["controls"])
    assert len(ObservationLedger(home).receipts("run-1")) == 2
    assert verify_store(home)["internal_verdict"] in ("MATCH", "UNVERIFIABLE")
    assert not verify_store(home)["findings"]
    report = render_report(res)
    assert "not observable from outside:" in report and "SUMMARY_ONLY_CHANNEL" in report
    gate = Monitor(home, clock=CLOCK).gate(read_call(tmp_path), ctx(tmp_path))
    assert gate.verdict == ALLOW


def test_flagged_trajectory_holds_next_call_until_owner_decides(tmp_path):
    home = tmp_path / "mon"
    t = turn("openai_responses_summary.json")
    res = observe_run(home, run_id="run-1", provider="openai", turns=[t], observed_on="2026-10-01",
                      extra_findings=[monitor_hook.Finding("trace/owner-component", "test finding",
                                                           {"k": 1})])
    assert len(res["holds"]) == 1
    mon = Monitor(home, clock=CLOCK)
    gate = mon.gate(read_call(tmp_path), ctx(tmp_path))
    assert gate.verdict == HOLD and not gate.run
    assert any(r["family"] == "trace-flag" for r in gate.assessment.reasons)
    # a different run is not held by this run's flag
    other = RunContext(run_id="run-2", workspace=str(tmp_path / "ws"))
    assert Monitor(home, clock=CLOCK).gate(read_call(tmp_path), other).verdict == ALLOW
    Escalator(home, CLOCK).decide(gate.hold_id, "APPROVED_ONCE", decider="owner")
    nxt = Monitor(home, clock=CLOCK).gate(
        ProposedCall(tool="list_dir", args={"path": str(tmp_path / "ws")}, seq=2, tool_use_id="t2"),
        ctx(tmp_path))
    assert nxt.verdict == ALLOW
    v = verify_store(home)
    assert not v["findings"], v


def test_expiry_does_not_clear_a_flag(tmp_path):
    home = tmp_path / "mon"
    trace_flag.raise_trace_flag(home, run_id="run-1", rule_id="trace/x", channel="none",
                                access_class="A0", evidence_sha256="0" * 64, raised_at=CLOCK())
    gate = Monitor(home, clock=CLOCK).gate(read_call(tmp_path), ctx(tmp_path))
    Escalator(home, CLOCK).decide(gate.hold_id, "EXPIRED", decider="system:expiry")
    again = Monitor(home, clock=CLOCK).gate(
        ProposedCall(tool="list_dir", args={"path": "x"}, seq=2, tool_use_id="t2"), ctx(tmp_path))
    assert again.verdict == HOLD


def test_documentation_drift_and_control_failure_become_findings():
    drift = monitor_hook.findings_from_measured_gap({"provider": "openai",
                                                     "documentation_drift": ["reasoning_text"]})
    assert drift[0].rule_id == "trace/documentation-drift"
    failed = monitor_hook.findings_from_controls("c", [{"control_id": "F1", "passed": "false"}])
    assert failed[0].evidence["failed"] == ["F1"]
    assert monitor_hook.findings_from_controls("c", [{"control_id": "F1", "passed": "true"}]) == []


def test_agent_cannot_clear_its_flag_by_writing_the_monitor_home(tmp_path):
    home = tmp_path / "mon"
    trace_flag.raise_trace_flag(home, run_id="run-1", rule_id="trace/x", channel="none",
                                access_class="A0", evidence_sha256="1" * 64, raised_at=CLOCK())
    write = ProposedCall(tool="write_file", args={"path": str(home / "pending.json"), "content": "{}"},
                         seq=1, tool_use_id="w1")
    gate = Monitor(home, clock=CLOCK).gate(write, ctx(tmp_path))
    assert gate.verdict != ALLOW and not gate.run


def test_receipt_refuses_floats_and_tampering_is_drift(tmp_path):
    with pytest.raises(FloatInReceipt):
        build_receipt(run_id="r", component="c", subject={}, inputs={}, result={"rate": 0.5},
                      gaps=[], does_not_prove="x")
    home = tmp_path / "mon"
    seal = ObservationLedger(home).append(build_receipt(
        run_id="r", component="c", subject={}, inputs={}, result={"rate": "0.5000"}, gaps=[],
        does_not_prove="x"))
    assert ObservationLedger(home).verify(seal)
    p = home / "records.jsonl"
    p.write_text(p.read_text(encoding="utf-8").replace("0.5000", "0.9000"), encoding="utf-8")
    assert verify_store(home)["verdict"] == "DRIFT"


def test_flag_is_not_registered_when_the_record_cannot_be_written(tmp_path):
    home = tmp_path / "mon"
    home.mkdir()
    (home / "records.jsonl").mkdir()          # the store path is a directory: append fails
    with pytest.raises(Exception):
        trace_flag.raise_trace_flag(home, run_id="run-1", rule_id="trace/x", channel="none",
                                    access_class="A0", evidence_sha256="2" * 64, raised_at=CLOCK())
    assert not (home / "pending.json").exists()


# --- review fixes (PR 317 independent review) ---------------------------------

def _egress(seq):
    return ProposedCall(tool="bash", args={"command": "curl https://example.org/x"}, seq=seq,
                        tool_use_id=f"e{seq}")


def test_an_earlier_grant_does_not_admit_a_call_past_a_newer_flag(tmp_path):
    """Owner approves call X (held for egress). A flag is raised before X is
    retried. The grant predates the flag, so it must not admit X past it."""
    home = tmp_path / "mon"
    first = Monitor(home, clock=CLOCK).gate(_egress(1), ctx(tmp_path))
    assert first.verdict == HOLD
    assert not any(r["family"] == "trace-flag" for r in first.assessment.reasons)
    Escalator(home, CLOCK).decide(first.hold_id, "APPROVED_ONCE", decider="owner")
    trace_flag.raise_trace_flag(home, run_id="run-1", rule_id="trace/x", channel="none",
                                access_class="A0", evidence_sha256="3" * 64, raised_at=CLOCK())
    retry = Monitor(home, clock=CLOCK).gate(_egress(2), ctx(tmp_path))
    assert retry.verdict == HOLD and not retry.run and not retry.redeemed_hold_id
    assert any(r["family"] == "trace-flag" for r in retry.assessment.reasons)
    # deciding the hold that cites the flag clears it; the call then redeems
    Escalator(home, CLOCK).decide(retry.hold_id, "APPROVED_ONCE", decider="owner")
    again = Monitor(home, clock=CLOCK).gate(_egress(3), ctx(tmp_path))
    assert again.verdict == ALLOW and again.redeemed_hold_id
    assert not verify_store(home)["findings"]


def test_a_flag_hit_with_no_sealed_flag_record_is_drift(tmp_path):
    """An index entry nobody sealed (written around raise_trace_flag) still
    holds the call, and verify reports the hold as unbacked."""
    home = tmp_path / "mon"
    esc = Escalator(home, CLOCK)
    index = esc._read_index()
    index["trace_flags"] = {"run-1": {"tf_forged": {"rule_id": "x", "channel": "none",
                                                   "access_class": "A0", "record_sha256": ""}}}
    esc._write_index(index)
    gate = Monitor(home, clock=CLOCK).gate(read_call(tmp_path), ctx(tmp_path))
    assert gate.verdict == HOLD
    v = verify_store(home)
    assert v["verdict"] == "DRIFT"
    assert [f["cause"] for f in v["findings"]] == ["TRACE_FLAG_HIT_UNBACKED"]


def test_a_flag_citing_a_receipt_the_chain_lacks_is_drift(tmp_path):
    home = tmp_path / "mon"
    trace_flag.raise_trace_flag(home, run_id="run-1", rule_id="trace/x", channel="none",
                                access_class="A0", evidence_sha256="4" * 64, raised_at=CLOCK(),
                                observation_receipt_sha256="f" * 64)
    causes = [f["cause"] for f in verify_store(home)["findings"]]
    assert causes == ["TRACEFLAG_RECEIPT_MISSING"]


def test_sandbagging_completion_gap_raises_a_finding_and_no_result_pairs_do_not():
    from harness.trace_observation import controls
    from harness.trace_observation.behavioral import observation as obs
    # compliance identical in every arm; the review arm stops completing on 12 of 40
    sandbag = obs.analyze([controls._fam(i, True, True, completed_review=i >= 12) for i in range(40)])
    assert sandbag["gaps"]["review-non_review"]["excludes_zero"] == "false"
    rules = [f.rule_id for f in monitor_hook.findings_from_observation(sandbag)]
    assert rules == ["trace/completion-gap"]
    both_fail = obs.analyze(controls._families(40, 0, all_fail=True))
    assert monitor_hook.findings_from_observation(both_fail) == []
    planted = obs.analyze(controls._families(40, 0.3))
    assert [f.rule_id for f in monitor_hook.findings_from_observation(planted)] == \
        ["trace/observation-gap"]
