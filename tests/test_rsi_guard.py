# SPDX-License-Identifier: MIT
"""Pytest suite for hardened harness.rsi_guard v2 (0 skips, <= 250 LOC)."""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

import pytest

from harness import rsi_guard as rg


def _make_receipt(tmp_path: Path, task_id: str = "t-1", verdict: str = "MATCH") -> dict:
    art = tmp_path / f"{task_id}.bld"
    art.write_text("fn main() {}\n", encoding="utf-8")
    raw = art.read_bytes()
    art_sha = "sha256:" + hashlib.sha256(raw).hexdigest()
    subject = {
        "engine": "buildlang", "flagship": "flywheel", "task_id": task_id,
        "git": {"commit": "a" * 40, "short_commit": "aaaaaaa", "branch": "main", "subject": "ok"},
        "artifacts": [{"rel_path": art.name, "sha256": art_sha, "bytes": len(raw)}],
        "oracle_command": ["buildc", "check", art.name],
    }
    oracle_claim = {"exit_code": 0, "stdout_sha256": "sha256:" + "0" * 64, "stderr_sha256": "sha256:" + "0" * 64, "pass_lines": 1, "fail_lines": 0}
    scope = ["engine=buildlang; staged test receipt"]
    claim = {"subject": subject, "verdict": verdict, "oracle": oracle_claim, "scope": scope}
    digests = rg.compute_engine_receipt_digests(subject, claim)
    return {
        "schema": rg.ENGINE_RECEIPT_SCHEMA, "subject": subject, "verdict": verdict,
        "oracle": oracle_claim, "artifact_paths": {art.name: str(art)}, "scope": scope, "digests": digests,
    }


def test_valve_accepts_genuine_verified_step() -> None:
    dec = rg.evaluate_rsi_step(rg.CandidateStep("s1", "compiler", 0.90, 0.88, "oracle-v1", True, False, False, 2.6, 0.72))
    assert dec.accepted and dec.action == "ACCEPT" and dec.reasons == ()


def test_valve_rejects_missing_oracle_failed_oracle_and_goodhart() -> None:
    assert "MISSING_INDEPENDENT_ORACLE" in rg.evaluate_rsi_step(rg.CandidateStep("s2", "compiler", 0.95)).reasons
    assert "ORACLE_VERIFICATION_FAILED" in rg.evaluate_rsi_step(rg.CandidateStep("s3", "math", 0.99, 0.95, "o1", False)).reasons
    dec = rg.evaluate_rsi_step(rg.CandidateStep("s4", "math", 0.99, 0.20, "o1", True))
    assert not dec.accepted and "GOODHART_PROXY_GAMING" in dec.reasons and dec.proxy_oracle_gap == 0.79


def test_valve_honest_exit_fabrication_and_j13_thresholds() -> None:
    ex = rg.evaluate_rsi_step(rg.CandidateStep("s5", "gov", 0.0, unsolvable_task=True, honest_exit=True))
    assert not ex.accepted and ex.action == "HONEST_EXIT"
    fab = rg.evaluate_rsi_step(rg.CandidateStep("s6", "gov", 0.99, 0.99, "o1", True, unsolvable_task=True, honest_exit=False))
    assert not fab.accepted and "UNSOLVABLE_FABRICATION_ATTEMPT" in fab.reasons
    rc = rg.evaluate_rsi_step(rg.CandidateStep("s7", "phys", 0.91, 0.89, "o1", True, effective_rank=1.4, top1_energy=0.70))
    ts = rg.evaluate_rsi_step(rg.CandidateStep("s8", "phys", 0.91, 0.89, "o1", True, effective_rank=2.5, top1_energy=0.92))
    assert "EPIGENETIC_RANK_COLLAPSE" in rc.reasons and "EPIGENETIC_TOP1_SPIKE" in ts.reasons


@pytest.mark.parametrize("bad_num", [float("nan"), float("inf"), float("-inf"), True])
def test_valve_rejects_non_finite_ieee754_inputs_fail_closed(bad_num: object) -> None:
    d1 = rg.evaluate_rsi_step(rg.CandidateStep("nf1", "fuzz", bad_num, 0.5, "o1", True))  # type: ignore[arg-type]
    d2 = rg.evaluate_rsi_step(rg.CandidateStep("nf2", "fuzz", 0.5, bad_num, "o1", True))  # type: ignore[arg-type]
    d3 = rg.evaluate_rsi_step(rg.CandidateStep("nf3", "fuzz", 0.5, 0.5, "o1", True, effective_rank=bad_num))  # type: ignore[arg-type]
    d4 = rg.evaluate_rsi_step(rg.CandidateStep("nf4", "fuzz", 0.5, 0.5, "o1", True, top1_energy=bad_num))  # type: ignore[arg-type]
    assert not d1.accepted and "NON_FINITE_PROXY_SCORE" in d1.reasons
    assert not d2.accepted and "NON_FINITE_ORACLE_SCORE" in d2.reasons
    assert not d3.accepted and "NON_FINITE_EFFECTIVE_RANK" in d3.reasons
    assert not d4.accepted and "NON_FINITE_TOP1_ENERGY" in d4.reasons


def test_valve_catches_overflowing_finite_difference_gap() -> None:
    dec = rg.evaluate_rsi_step(rg.CandidateStep("ovf", "fuzz", 1e308, -1e308, "o1", True))
    assert not dec.accepted and "NON_FINITE_PROXY_ORACLE_GAP" in dec.reasons


def test_sta070_arm_a_collapses_while_arm_b_compounds_cleanly() -> None:
    sim = rg.simulate_arm_a_vs_arm_b(generations=20)
    assert sim["arm_a"]["final_capability"] < 0.0 and sim["arm_a"]["hacks_accepted"] == 40
    assert sim["arm_b"]["final_capability"] > 2.5 and sim["arm_b"]["hacks_accepted"] == 0
    assert sim["arm_b"]["fabrications"] == 0 and sim["arm_b"]["honest_exits"] == 20 and sim["arm_b"]["monotone_ok"] is True


def test_drift_monitor_passes_healthy_series_and_catches_regressions() -> None:
    assert rg.assess_series([rg.StepTelemetry(i, 1.0 + 0.05 * i, 2.4, 2.6) for i in range(1, 7)])["ok"] is True
    assert any(a["code"] == "CAPABILITY_BELOW_FLOOR" for a in rg.assess_series([rg.StepTelemetry(1, 0.95, 2.2), rg.StepTelemetry(2, 0.82, 2.2)])["alerts"])
    pts_reg = [rg.StepTelemetry(1, 1.0, 2.3), rg.StepTelemetry(2, 1.4, 2.3), rg.StepTelemetry(3, 1.25, 2.3)]
    assert any(a["code"] == "SILENT_REGRESSION_FROM_PEAK" for a in rg.assess_series(pts_reg)["alerts"])
    assert any(a["code"] == "ENTROPY_COLLAPSE" for a in rg.assess_series([rg.StepTelemetry(i, 1.0 + 0.01 * i, 0.8) for i in range(1, 5)])["alerts"])
    osc = [rg.StepTelemetry(i + 1, c, 2.3) for i, c in enumerate([1.00, 1.03, 1.00, 1.03, 1.00])]
    assert any(a["code"] == "OSCILLATION_LOOP_DETECTED" for a in rg.assess_series(osc)["alerts"])


@pytest.mark.parametrize("bad_num", [float("nan"), float("inf"), float("-inf"), True])
def test_drift_monitor_rejects_non_finite_ieee754_telemetry(bad_num: object) -> None:
    r1 = rg.assess_series([rg.StepTelemetry(1, bad_num, 2.2, 2.5)])  # type: ignore[arg-type]
    r2 = rg.assess_series([rg.StepTelemetry(1, 1.0, bad_num, 2.5)])  # type: ignore[arg-type]
    r3 = rg.assess_series([rg.StepTelemetry(1, 1.0, 2.2, bad_num)])  # type: ignore[arg-type]
    assert not r1["ok"] and any(a["code"] == "NON_FINITE_CAPABILITY" for a in r1["alerts"])
    assert not r2["ok"] and any(a["code"] == "NON_FINITE_ENTROPY_BITS" for a in r2["alerts"])
    assert not r3["ok"] and any(a["code"] == "NON_FINITE_EFFECTIVE_RANK" for a in r3["alerts"])


def test_drift_monitor_empty_bad_window_and_non_monotonic_rank_drift() -> None:
    assert rg.assess_series([])["ok"] is False
    with pytest.raises(ValueError, match="window"):
        rg.DriftMonitor(rg.DriftPolicy(window=1))
    codes = {a["code"] for a in rg.assess_series([rg.StepTelemetry(2, 1.0, 2.2, 2.5), rg.StepTelemetry(2, 1.02, 2.2, 1.3)])["alerts"]}
    assert {"NON_MONOTONIC_STEP", "EPIGENETIC_RANK_DRIFT"} <= codes


@pytest.mark.parametrize("edge_val", [0.0, -0.0, 5e-324, 1e-6, 0.90, float((1 << 53) + 1)])
def test_valve_handles_finite_ieee754_edges_without_crashing(edge_val: float) -> None:
    dec = rg.evaluate_rsi_step(rg.CandidateStep("edge", "fuzz", edge_val, edge_val, "o1", True))
    assert dec.accepted is True and dec.proxy_oracle_gap == 0.0


def test_receipt_bridge_verifies_and_rejects_tamper(tmp_path: Path) -> None:
    rec = _make_receipt(tmp_path, "valid-1")
    assert rg.verify_engine_receipt(rec, check_files=True, artifact_root=tmp_path) == (True, [])
    assert "VERDICT_NOT_MATCH:DRIFT" in rg.verify_engine_receipt(_make_receipt(tmp_path, "d-1", "DRIFT"))[1]
    t_claim = copy.deepcopy(rec)
    t_claim["verdict"] = "DRIFT"
    assert "DIGEST_MISMATCH:claim_sha256" in rg.verify_engine_receipt(t_claim, require_match=False)[1]
    t_env = copy.deepcopy(rec)
    t_env["digests"]["envelope_sha256"] = "sha256:" + ("f" * 64)
    assert "DIGEST_MISMATCH:envelope_sha256" in rg.verify_engine_receipt(t_env)[1]
    (tmp_path / "valid-1.bld").write_text("fn main() { /* mutated */ }\n", encoding="utf-8")
    assert any(e.startswith("ARTIFACT_HASH_MISMATCH:") for e in rg.verify_engine_receipt(rec, check_files=True, artifact_root=tmp_path)[1])


def test_receipt_ledger_chain_replay_and_tamper(tmp_path: Path) -> None:
    ledger = tmp_path / "rsi_ledger.jsonl"
    r1 = _make_receipt(tmp_path, "r1")
    rg.append_verified_receipt_to_ledger(ledger, r1, check_files=True, artifact_root=tmp_path)
    rg.append_verified_receipt_to_ledger(ledger, _make_receipt(tmp_path, "r2"), check_files=True, artifact_root=tmp_path)
    ok, verdict, root = rg.verify_receipt_ledger(ledger)
    assert ok and verdict == "MATCH" and root.startswith("sha256:")
    with pytest.raises(ValueError, match="DUPLICATE_CLAIM_REPLAY"):
        rg.append_verified_receipt_to_ledger(ledger, r1)
    ledger.write_text(ledger.read_text(encoding="utf-8").replace("r1", "r9", 1), encoding="utf-8")
    assert rg.verify_receipt_ledger(ledger)[1] == "ENTRY_DIGEST_TAMPERED_AT_0"
    assert rg.verify_receipt_ledger(tmp_path / "missing.jsonl")[0] is False


def test_rsi_guard_spdx_limits_and_hygiene() -> None:
    assert len(rg.HONEST_SCOPE_LIMITS) == 3
    stage_root = Path(__file__).resolve().parent.parent
    files = sorted((stage_root / "harness" / "rsi_guard").glob("*.py")) + [Path(__file__).resolve()]
    local_path_re = re.compile(r"[A-Za-z]:\\(?:dev|Users)\\")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 250, f"{path.name} exceeds 250-line budget"
        assert "SPDX-License-Identifier: MIT" in text
        assert "\u2014" not in text and "\u2013" not in text
        assert not local_path_re.search(text)
