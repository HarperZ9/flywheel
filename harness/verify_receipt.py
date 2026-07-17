"""verify_receipt.py — re-run a proof receipt's check offline and confirm it holds.

The whole thesis is a re-checkable receipt; this is the one-command form. Given a
receipt (ProofEnvelope) and the task it was produced against, re-run the oracle on
the receipt's candidate and confirm the recorded verdict and canonical output hash
reproduce. MATCH means a stranger got the same answer offline; DRIFT means the
receipt does not hold.

    python -m harness.verify_receipt --receipt r.json --task-dir ./task
"""
from __future__ import annotations

import argparse
import json

from .envelope import load_envelope
from .task import load_task


def verify_envelope(envelope, task, *, oracle=None) -> dict:
    """Re-run the receipt's oracle on its candidate; MATCH iff verdict and output
    hash both reproduce. Inject `oracle` for tests; default is PytestOracle."""
    if oracle is None:
        from .oracle import PytestOracle
        oracle = PytestOracle()
    res = oracle.verify(envelope.candidate, task)
    checks = {
        "verdict_matches": res.verdict() == envelope.verdict,
        "output_hash_matches": res.output_hash == envelope.oracle_output_hash,
    }
    return {
        "schema": "flywheel.receipt-verification/v1",
        "verdict": "MATCH" if all(checks.values()) else "DRIFT",
        "checks": checks,
        "claimed": {"verdict": envelope.verdict, "output_hash": envelope.oracle_output_hash},
        "recomputed": {"verdict": res.verdict(), "output_hash": res.output_hash},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="re-check a Flywheel proof receipt offline")
    ap.add_argument("--receipt", required=True, help="path to the ProofEnvelope JSON")
    ap.add_argument("--task-dir", required=True, help="the task directory (test files + task.json)")
    a = ap.parse_args(argv)
    result = verify_envelope(load_envelope(a.receipt), load_task(a.task_dir))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
