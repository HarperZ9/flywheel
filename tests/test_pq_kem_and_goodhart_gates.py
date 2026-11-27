# SPDX-License-Identifier: MIT
"""Unit, adversarial, and 400-trial fuzz tests for pq_kem_attest and rlvr_goodhart_gate."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any

import pytest

from harness.pq_kem_attest import (
    MLKEM_K,
    MLKEM_N,
    MLKEM_Q,
    PqKemPolicy,
    REQUIRED_FO_CONTROLS,
    REQUIRED_ISAS,
    parse_pq_kem_payload,
    parse_pq_kem_receipt,
    verify_pq_kem_bundle,
    verify_pq_kem_file,
)
from harness.pq_kem_attest.pq_oracle import main as pq_main
from harness.rlvr_goodhart_gate import (
    GoodhartPolicy,
    parse_goodhart_payload,
    verify_goodhart_bundle,
    verify_goodhart_file,
)
from harness.rlvr_goodhart_gate.goodhart_oracle import main as gh_main


def _hex64(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _valid_pq_payload() -> dict[str, Any]:
    return {
        "schema": "pq-hybrid-kem-bundle/1",
        "verdict": "MATCH",
        "oracle_exit_code": 0,
        "claim_sha256": f"sha256:{_hex64('claim')}",
        "params": {"q": MLKEM_Q, "n": MLKEM_N, "k": MLKEM_K},
        "hybrid_committed": 1,
        "coefficients": [(i * 13) % MLKEM_Q for i in range(MLKEM_N)],
        "binaries": [
            {"isa": isa, "rel_path": f"bin/{isa}.bin", "bytes": 25674 + i * 1000, "sha256": _hex64(isa)}
            for i, isa in enumerate(REQUIRED_ISAS)
        ],
        "fo_controls": [
            {"name": name, "rejected": True, "hybrid_committed": 0, "error_code": -101 - i * 100, "isas_rejected": 5}
            for i, name in enumerate(REQUIRED_FO_CONTROLS)
        ],
    }


def _valid_goodhart_payload() -> dict[str, Any]:
    return {
        "schema": "wave131a-test-time-mcts-oracle/1",
        "ok": True,
        "verdict": "PASS",
        "mcts_hacked_accepted": 0,
        "goodhart_blocked": 90,
        "greedy_hacked": 90,
        "monotonic_ok": True,
        "round0_rate": 0.125,
        "final_rate": 1.0,
        "mean_trap_prob": 0.0042,
        "max_3way_err": 2.8e-14,
        "controls_caught": 3,
        "controls_total": 3,
        "solve_curve": [0.125, 0.375, 0.75, 1.0],
        "candidates": [
            {"candidate_id": "ok_1", "prm_score": 0.94, "oracle_score": 1.0, "accepted": True, "quarantined": False, "assigned_value": 1.0},
            {"candidate_id": "trap_1", "prm_score": 0.96, "oracle_score": 0.0, "accepted": False, "quarantined": True, "assigned_value": -1.0},
        ],
        "policy_updates": [
            {"step": 1, "oracle_score": 1.0, "weight_delta": 0.15, "blocked": False},
            {"step": 2, "oracle_score": 0.0, "weight_delta": 0.0, "blocked": True},
        ],
    }


def test_pq_kem_happy_path_and_receipt_envelope(tmp_path: Path) -> None:
    rep = verify_pq_kem_bundle(parse_pq_kem_payload(_valid_pq_payload()), PqKemPolicy(require_coefficients=True))
    assert rep.ok and rep.verdict == "PASS" and rep.fo_controls_verified == 4 and rep.coeffs_checked == 256
    assert len(rep.isas_verified) == 5 and len(rep.report_sha256) == 64
    suffixes = {"x64-pe": ".exe", "x64-elf": ".x64.elf", "rv64-elf": ".rv64.elf", "aarch64-elf": ".aarch64.elf", "wasm": ".wasm"}
    artifacts = []
    for isa, suf in suffixes.items():
        fp = tmp_path / f"kem{suf}"
        data = f"binary-{isa}".encode("utf-8")
        fp.write_bytes(data)
        artifacts.append({"rel_path": fp.name, "bytes": len(data), "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}"})
    receipt = {
        "schema": "engine-receipt/1",
        "verdict": "MATCH",
        "digests": {"claim_sha256": f"sha256:{_hex64('slice29')}"},
        "oracle": {"exit_code": 0, "stdout_excerpt": '{"q": 3329, "n": 256, "k": 2, "hybrid_committed": 1}'},
        "subject": {"artifacts": artifacts},
    }
    rec_path = tmp_path / "rec.json"
    supp_path = tmp_path / "supp.json"
    rec_path.write_text(json.dumps(receipt), encoding="utf-8")
    supp_path.write_text(json.dumps({"fo_controls": _valid_pq_payload()["fo_controls"]}), encoding="utf-8")
    disk_rep = verify_pq_kem_file(rec_path, supp_path, PqKemPolicy(check_on_disk=True), artifact_root=tmp_path)
    assert disk_rep.ok and len(disk_rep.isas_verified) == 5
    (tmp_path / "kem.wasm").write_bytes(b"tampered")
    bad_rep = verify_pq_kem_file(rec_path, supp_path, PqKemPolicy(check_on_disk=True), artifact_root=tmp_path)
    assert not bad_rep.ok and any("sha256_mismatch:wasm" in e for e in bad_rep.errors)


@pytest.mark.parametrize(
    ("mutator", "expected_prefix"),
    [
        (lambda d: d["params"].update({"q": 3330}), "invalid_mlkem_q"),
        (lambda d: d["params"].update({"n": 128}), "invalid_mlkem_n"),
        (lambda d: d["params"].update({"k": 3}), "invalid_mlkem_k"),
        (lambda d: d["coefficients"].__setitem__(7, 3329), "coeff_out_of_range"),
        (lambda d: d["coefficients"].__setitem__(0, -1), "coeff_out_of_range"),
        (lambda d: d["coefficients"].__setitem__(1, True), "coeff_non_int"),
        (lambda d: d["binaries"].pop(), "missing_isa:wasm"),
        (lambda d: d["binaries"][0].update({"sha256": "deadbeef"}), "invalid_sha256"),
        (lambda d: d["binaries"][4].update({"bytes": 99999}), "wasm_exceeds_budget"),
        (lambda d: d["fo_controls"][0].update({"rejected": False}), "fo_control_not_rejected"),
        (lambda d: d["fo_controls"][1].update({"hybrid_committed": 1}), "fo_control_hybrid_committed"),
        (lambda d: d["fo_controls"][2].update({"error_code": 0}), "fo_control_non_negative_code"),
        (lambda d: d["fo_controls"][3].update({"isas_rejected": 4}), "fo_control_isa_count"),
        (lambda d: d["fo_controls"].pop(), "fo_control_missing"),
        (lambda d: d.update({"verdict": "DRIFT"}), "invalid_verdict"),
        (lambda d: d.update({"oracle_exit_code": 1}), "nonzero_oracle_exit"),
    ],
)
def test_pq_kem_planted_attacks_fail_closed(mutator: Any, expected_prefix: str) -> None:
    payload = _valid_pq_payload()
    mutator(payload)
    rep = verify_pq_kem_bundle(parse_pq_kem_payload(payload))
    assert not rep.ok and rep.verdict == "REJECT"
    assert any(expected_prefix in e for e in rep.errors), rep.errors


def test_goodhart_happy_path_and_cli(tmp_path: Path) -> None:
    payload = _valid_goodhart_payload()
    rep = verify_goodhart_bundle(parse_goodhart_payload(payload))
    assert rep.ok and rep.verdict == "PASS" and rep.goodhart_bypasses == 0 and rep.goodhart_traps_caught == 91
    rp = tmp_path / "goodhart.json"
    rec = tmp_path / "rec.json"
    rp.write_text(json.dumps(payload), encoding="utf-8")
    rec.write_text(json.dumps({"schema": "engine-receipt/1", "verdict": "MATCH", "oracle": {"exit_code": 0}}), encoding="utf-8")
    assert verify_goodhart_file(rp, rec).ok
    assert gh_main([str(rp), "--receipt", str(rec)]) == 0
    pq_p = tmp_path / "pq.json"
    pq_p.write_text(json.dumps(_valid_pq_payload()), encoding="utf-8")
    assert pq_main([str(pq_p)]) == 0
    bad_pq = _valid_pq_payload()
    bad_pq["params"]["q"] = 17
    pq_p.write_text(json.dumps(bad_pq), encoding="utf-8")
    assert pq_main([str(pq_p)]) == 2


@pytest.mark.parametrize(
    ("mutator", "expected_prefix"),
    [
        (lambda d: d["candidates"][1].update({"accepted": True}), "goodhart_bypass_accepted"),
        (lambda d: d["candidates"][1].update({"quarantined": False}), "goodhart_trap_not_quarantined"),
        (lambda d: d["candidates"][1].update({"assigned_value": 0.5}), "goodhart_non_negative_val"),
        (lambda d: d["candidates"][1].update({"prm_score": 0.90, "accepted": True}), "goodhart_bypass_accepted"),
        (lambda d: d["candidates"][1].update({"prm_score": math.nan}), "invalid_prm_score"),
        (lambda d: d["candidates"][0].update({"oracle_score": math.inf}), "invalid_oracle_score"),
        (lambda d: d["candidates"].append({"candidate_id": "low_acc", "prm_score": 0.4, "oracle_score": 0.0, "accepted": True, "quarantined": False}), "unverified_oracle_zero_accepted"),
        (lambda d: d["policy_updates"][1].update({"weight_delta": 0.01}), "unverified_weight_drift"),
        (lambda d: d["policy_updates"][1].update({"blocked": False}), "unverified_update_not_blocked"),
        (lambda d: d["solve_curve"].__setitem__(2, 0.2), "solve_rate_regressed"),
        (lambda d: d.update({"mcts_hacked_accepted": 1}), "mcts_hacked_accepted_nonzero"),
        (lambda d: d.update({"goodhart_blocked": 89}), "goodhart_blocked_below_greedy_hacked"),
        (lambda d: d.update({"max_3way_err": 1e-9}), "parity_err_exceeds_limit"),
        (lambda d: d.update({"monotonic_ok": False}), "rlvr_non_monotonic"),
        (lambda d: d.update({"mean_trap_prob": 0.08}), "trap_prob_above_limit"),
        (lambda d: d.update({"controls_caught": 2}), "controls_incomplete"),
    ],
)
def test_goodhart_planted_attacks_fail_closed(mutator: Any, expected_prefix: str) -> None:
    payload = _valid_goodhart_payload()
    mutator(payload)
    rep = verify_goodhart_bundle(parse_goodhart_payload(payload))
    assert not rep.ok and rep.verdict == "REJECT"
    assert any(expected_prefix in e for e in rep.errors), rep.errors


def test_adversarial_400_trial_fuzz_zero_bypasses() -> None:
    rng = random.Random(20261127)
    pq_bypasses = 0
    for trial in range(200):
        p = _valid_pq_payload()
        kind = trial % 5
        if kind == 0:
            p["coefficients"][rng.randrange(MLKEM_N)] = rng.choice([-99, -1, 3329, 4096, True, "bad"])
        elif kind == 1:
            p["params"][rng.choice(["q", "n", "k"])] = rng.choice([0, -1, 17, 3328, False])
        elif kind == 2:
            ctrl = p["fo_controls"][rng.randrange(4)]
            fld = rng.choice(["rejected", "hybrid_committed", "error_code"])
            ctrl[fld] = False if fld == "rejected" else (1 if fld == "hybrid_committed" else 0)
        elif kind == 3:
            p["binaries"][rng.randrange(5)]["sha256"] = f"zz{trial}"
        else:
            p["binaries"].pop(rng.randrange(len(p["binaries"])))
        if verify_pq_kem_bundle(parse_pq_kem_payload(p)).ok:
            pq_bypasses += 1
    gh_bypasses = 0
    for trial in range(200):
        g = _valid_goodhart_payload()
        kind = trial % 5
        if kind == 0:
            prm = round(0.90 + rng.random() * 0.10, 6)
            g["candidates"].append({"candidate_id": f"f{trial}", "prm_score": prm, "oracle_score": 0.0, "accepted": True, "quarantined": False, "assigned_value": 1.0})
        elif kind == 1:
            g["candidates"].append({"candidate_id": f"q{trial}", "prm_score": 0.95, "oracle_score": 0.0, "accepted": False, "quarantined": False, "assigned_value": 0.2})
        elif kind == 2:
            g["candidates"].append({"candidate_id": f"n{trial}", "prm_score": rng.choice([math.nan, math.inf, -0.1, 1.2, True]), "oracle_score": 1.0, "accepted": True, "quarantined": False})
        elif kind == 3:
            g["policy_updates"].append({"step": trial, "oracle_score": 0.0, "weight_delta": rng.uniform(1e-6, 0.5), "blocked": True})
        else:
            g["max_3way_err"] = rng.choice([1e-9, math.nan, -1e-12, 0.01])
        if verify_goodhart_bundle(parse_goodhart_payload(g), GoodhartPolicy()).ok:
            gh_bypasses += 1
    assert pq_bypasses == 0 and gh_bypasses == 0
    assert parse_pq_kem_receipt({"schema": "engine-receipt/1", "verdict": "DRIFT"}).verdict == "DRIFT"
