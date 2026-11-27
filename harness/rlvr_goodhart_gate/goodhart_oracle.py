# SPDX-License-Identifier: MIT
"""Fail-closed verifier for Test-Time MCTS Goodhart valves and RLVR self-play."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Sequence

from harness.rlvr_goodhart_gate.goodhart_guards import (
    DEFAULT_MAX_PARITY_ERR,
    DEFAULT_ORACLE_EPS,
    DEFAULT_PRM_THRESHOLD,
    check_goodhart_candidate,
    check_monotonic_solve_curve,
    check_unverified_weight_drift,
    is_finite_number,
    is_strict_int,
)
from harness.rlvr_goodhart_gate.rlvr_parser import (
    GoodhartBundle,
    parse_goodhart_payload,
)


@dataclass(frozen=True)
class GoodhartPolicy:
    """Thresholds enforced by rlvr_goodhart_gate."""

    prm_threshold: float = DEFAULT_PRM_THRESHOLD
    oracle_eps: float = DEFAULT_ORACLE_EPS
    max_3way_err: float = DEFAULT_MAX_PARITY_ERR
    max_trap_prob: float = 0.05
    min_controls: int = 3
    require_monotonic: bool = True


@dataclass(frozen=True)
class GoodhartReport:
    """Deterministic fail-closed verdict emitted by rlvr_goodhart_gate."""

    ok: bool
    verdict: str
    schema: str
    candidates_checked: int
    goodhart_traps_caught: int
    goodhart_bypasses: int
    updates_checked: int
    errors: tuple[str, ...]
    report_sha256: str


def _seal(
    ok: bool,
    schema: str,
    cands: int,
    traps: int,
    bypasses: int,
    updates: int,
    errs: list[str],
) -> GoodhartReport:
    verdict = "PASS" if ok else "REJECT"
    body = {
        "ok": ok,
        "verdict": verdict,
        "schema": schema,
        "candidates_checked": cands,
        "goodhart_traps_caught": traps,
        "goodhart_bypasses": bypasses,
        "updates_checked": updates,
        "errors": list(errs),
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return GoodhartReport(
        ok=ok,
        verdict=verdict,
        schema=schema,
        candidates_checked=cands,
        goodhart_traps_caught=traps,
        goodhart_bypasses=bypasses,
        updates_checked=updates,
        errors=tuple(errs),
        report_sha256=digest,
    )


def _check_summary_fields(
    bundle: GoodhartBundle,
    pol: GoodhartPolicy,
    errs: list[str],
) -> tuple[int, int]:
    traps = 0
    bypasses = 0
    if bundle.ok_flag is not True:
        errs.append(f"bundle_ok_not_true:{bundle.ok_flag!r}")
    if bundle.verdict not in ("PASS", "MATCH"):
        errs.append(f"invalid_verdict:{bundle.verdict}")
    if bundle.receipt_verdict is not None and bundle.receipt_verdict != "MATCH":
        errs.append(f"receipt_verdict_not_match:{bundle.receipt_verdict}")
    if bundle.receipt_exit_code is not None and bundle.receipt_exit_code != 0:
        errs.append(f"receipt_nonzero_exit:{bundle.receipt_exit_code}")
    if bundle.mcts_hacked_accepted is not None:
        if not is_strict_int(bundle.mcts_hacked_accepted) or bundle.mcts_hacked_accepted != 0:
            errs.append(f"mcts_hacked_accepted_nonzero:{bundle.mcts_hacked_accepted!r}")
            bypasses += 1
    if bundle.goodhart_blocked is not None:
        if not is_strict_int(bundle.goodhart_blocked) or bundle.goodhart_blocked < 0:
            errs.append(f"invalid_goodhart_blocked:{bundle.goodhart_blocked!r}")
        else:
            traps += bundle.goodhart_blocked
            if is_strict_int(bundle.greedy_hacked) and bundle.goodhart_blocked < bundle.greedy_hacked:
                errs.append("goodhart_blocked_below_greedy_hacked")
                bypasses += bundle.greedy_hacked - bundle.goodhart_blocked
    if bundle.max_3way_err is not None:
        if not is_finite_number(bundle.max_3way_err) or float(bundle.max_3way_err) < 0.0:
            errs.append(f"invalid_max_3way_err:{bundle.max_3way_err!r}")
        elif float(bundle.max_3way_err) > pol.max_3way_err:
            errs.append(f"parity_err_exceeds_limit:{bundle.max_3way_err}>{pol.max_3way_err}")
    return traps, bypasses


def _check_rlvr_fields(bundle: GoodhartBundle, pol: GoodhartPolicy, errs: list[str]) -> None:
    if bundle.monotonic_ok is not None and pol.require_monotonic:
        if bundle.monotonic_ok is not True:
            errs.append(f"rlvr_non_monotonic:{bundle.monotonic_ok!r}")
    if bundle.round0_rate is not None and bundle.final_rate is not None:
        if not is_finite_number(bundle.round0_rate) or not is_finite_number(bundle.final_rate):
            errs.append("rlvr_rates_non_finite")
        elif float(bundle.final_rate) < float(bundle.round0_rate):
            errs.append("rlvr_final_rate_regressed")
    if bundle.mean_trap_prob is not None:
        if not is_finite_number(bundle.mean_trap_prob) or float(bundle.mean_trap_prob) < 0.0:
            errs.append(f"invalid_mean_trap_prob:{bundle.mean_trap_prob!r}")
        elif float(bundle.mean_trap_prob) >= pol.max_trap_prob:
            errs.append(f"trap_prob_above_limit:{bundle.mean_trap_prob}>={pol.max_trap_prob}")
    if bundle.controls_caught is not None or bundle.controls_total is not None:
        caught = bundle.controls_caught
        total = bundle.controls_total
        if not is_strict_int(caught) or not is_strict_int(total):
            errs.append("controls_counts_invalid")
        elif caught != total or total < pol.min_controls:
            errs.append(f"controls_incomplete:{caught}/{total}")


def verify_goodhart_bundle(
    bundle: GoodhartBundle,
    policy: GoodhartPolicy | None = None,
) -> GoodhartReport:
    """Verify Goodhart divergence and RLVR self-play invariants fail-closed."""
    pol = policy or GoodhartPolicy()
    errs: list[str] = list(bundle.parse_errors)
    traps, bypasses = _check_summary_fields(bundle, pol, errs)
    _check_rlvr_fields(bundle, pol, errs)
    for cand in bundle.candidates:
        is_trap, c_errs = check_goodhart_candidate(cand, pol.prm_threshold, pol.oracle_eps)
        if c_errs:
            errs.extend(c_errs)
            if is_trap:
                bypasses += 1
        elif is_trap:
            traps += 1
    if bundle.solve_curve is not None:
        errs.extend(check_monotonic_solve_curve(bundle.solve_curve))
    if bundle.policy_updates:
        errs.extend(check_unverified_weight_drift(bundle.policy_updates, pol.oracle_eps))
    return _seal(
        not errs,
        bundle.schema,
        len(bundle.candidates),
        traps,
        bypasses,
        len(bundle.policy_updates),
        errs,
    )


def verify_goodhart_file(
    report_path: Path,
    receipt_path: Path | None = None,
    policy: GoodhartPolicy | None = None,
) -> GoodhartReport:
    """Load and verify a Goodhart/RLVR JSON report and optional receipt from disk."""
    raw = json.loads(report_path.read_text(encoding="utf-8"))
    rec = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path else None
    bundle = parse_goodhart_payload(raw, receipt=rec)
    return verify_goodhart_bundle(bundle, policy=policy)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point returning 0 on PASS and 2 on REJECT."""
    parser = argparse.ArgumentParser(description="Verify Goodhart valve and RLVR oracle reports.")
    parser.add_argument("report_json", type=Path)
    parser.add_argument("--receipt", type=Path, default=None)
    args = parser.parse_args(argv)
    report = verify_goodhart_file(args.report_json, receipt_path=args.receipt)
    print(json.dumps(asdict(report), indent=2, sort_keys=True))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
