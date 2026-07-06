"""calibration.py — verifier calibration receipts. Who verifies the verifier?

Before an oracle is trusted in the accept path, prove it DISCRIMINATES: run it
against a labelled set of known-good and known-bad candidates and confirm it
accepts the good and — the fatal case — never accepts a known-bad. A false
positive (oracle passes a candidate that must fail) means the verifier can be
fooled; such an oracle is NOT trustworthy and must not gate acceptance.

This is NVIDIA's RL doctrine (calibrate the verifier against 50-100 manually
inspected outputs before trusting it) made a re-checkable receipt, and it is the
same discipline as the adversarial corpus one layer down: a verifier is credible
only if its refutation path provably fires. `require_calibrated` refuses to
proceed on an oracle with any false accept.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .oracle import Oracle
from .task import Task


@dataclass
class CalibrationCase:
    candidate: str
    should_pass: bool
    note: str = ""


@dataclass
class CalibrationReceipt:
    oracle_type: str
    n_cases: int
    true_pos: int
    true_neg: int
    false_pos: int          # accepted a known-bad — the fatal error
    false_neg: int          # rejected a known-good — costly, not fatal
    trustworthy: bool       # false_pos == 0
    accuracy: float
    receipt_hash: str
    detail: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("oracle_type", "n_cases", "true_pos", "true_neg", "false_pos",
                 "false_neg", "trustworthy", "accuracy", "receipt_hash")}


def calibrate(oracle: Oracle, task: Task,
              cases: list[CalibrationCase]) -> CalibrationReceipt:
    """Run the oracle against labelled cases and score its discrimination. The
    receipt is content-addressed over the (candidate-hash, expected, observed)
    triples, so the calibration is itself re-checkable."""
    tp = tn = fp = fn = 0
    detail = []
    triples = []
    for c in cases:
        passed = oracle.verify(c.candidate, task).passed
        if c.should_pass and passed:
            tp += 1; outcome = "TP"
        elif (not c.should_pass) and (not passed):
            tn += 1; outcome = "TN"
        elif (not c.should_pass) and passed:
            fp += 1; outcome = "FP"     # accepted a known-bad
        else:
            fn += 1; outcome = "FN"
        chash = hashlib.sha256(c.candidate.encode()).hexdigest()[:12]
        detail.append({"candidate_hash": chash, "should_pass": c.should_pass,
                       "passed": passed, "outcome": outcome, "note": c.note})
        triples.append((chash, c.should_pass, passed))
    n = len(cases)
    blob = json.dumps([oracle.oracle_type, sorted(map(list, triples))], sort_keys=True)
    rhash = hashlib.sha256(blob.encode()).hexdigest()[:16]
    return CalibrationReceipt(
        oracle_type=oracle.oracle_type, n_cases=n,
        true_pos=tp, true_neg=tn, false_pos=fp, false_neg=fn,
        trustworthy=(fp == 0 and n > 0),
        accuracy=round((tp + tn) / n, 3) if n else 0.0,
        receipt_hash=rhash, detail=detail)


class UncalibratedOracleError(RuntimeError):
    pass


def require_calibrated(oracle: Oracle, task: Task,
                       cases: list[CalibrationCase]) -> CalibrationReceipt:
    """Gate: return the receipt only if the oracle made ZERO false accepts.
    Raises otherwise — an oracle that accepts a known-bad must never gate the
    accept path."""
    r = calibrate(oracle, task, cases)
    if not r.trustworthy:
        raise UncalibratedOracleError(
            f"oracle '{oracle.oracle_type}' failed calibration: "
            f"{r.false_pos} false accept(s) over {r.n_cases} cases — untrustworthy")
    return r


def calibration_report(r: CalibrationReceipt) -> str:
    status = "TRUSTWORTHY" if r.trustworthy else "UNTRUSTWORTHY"
    return (f"verifier calibration [{r.oracle_type}]: {status} — "
            f"acc {r.accuracy}, {r.false_pos} false-accepts, {r.false_neg} "
            f"false-rejects over {r.n_cases} cases (receipt {r.receipt_hash})")
