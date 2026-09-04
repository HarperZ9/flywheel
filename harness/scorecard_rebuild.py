"""Rebuild a run scorecard from the attempt receipts already sealed on disk.

The executor seals every attempt as it finishes and writes the run-level
scorecard once, at the end. A run that raises after the last attempt therefore
leaves a full set of paid, sealed attempts and no document any reader can open.
That happened to the 2026-09-04 head-to-head: 35 attempts completed, the source
tree had been edited while they ran, and the drift guard raised before the
scorecard was written.

Retyping those rows by hand is what this module exists to prevent. Each receipt
carries its own final row plus a hash over that row and over every artifact
beside it, so the rows can be recovered and checked rather than transcribed. A
receipt whose hashes no longer agree with the bytes on disk is excluded and
named. It is never repaired, because a receipt that disagrees with its own
artifacts is evidence of drift and the drift is the finding.

What this does not do: it cannot tell you the run finished. A rebuild over the
receipts of an interrupted run reports the attempts that were sealed, and the
absent ones leave no trace here at all. The caller states the denominator.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.cross_harness_artifacts import recheck_attempt_receipt
from harness.cross_harness_run_seal import SCORECARD_SCHEMA as SCHEMA

RECEIPT_SCHEMA = "harness.cross-harness-attempt-receipt/v1"

DOES_NOT_PROVE = [
    "A rebuilt scorecard reports the attempts that were sealed. An attempt the "
    "run never reached leaves no receipt, so it is absent here rather than failed.",
    "Verifying a receipt says its row and its artifacts still agree with the "
    "hashes written when the attempt ended. It says nothing about whether the "
    "answer inside was right.",
]


def _read(path: Path) -> dict[str, Any] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def run_tree_state(run_root: Path) -> str:
    """What the run concluded about its own source tree, when it got that far.

    `unsealed` is the state this module was written for: the run raised before
    writing run.json, so nobody ever checked whether the tree that produced
    these attempts is the tree the rows name in `source_commit`.
    """
    run = _read(Path(run_root) / "run.json")
    if run is None:
        return "unsealed"
    state = run.get("source_tree_state")
    return state if isinstance(state, str) and state else "unrecorded"


def rebuild(run_root: Path) -> dict[str, Any]:
    """Recover every verifiable row under `run_root` into one scorecard.

    Rows come back sorted by the receipt path so the same run rebuilds to the
    same bytes, which is what lets a rebuild be re-run as a check rather than
    trusted as an event.
    """
    root = Path(run_root).resolve(strict=True)
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for receipt_path in sorted(root.rglob("receipt.json")):
        relative = receipt_path.relative_to(root).as_posix()
        receipt = _read(receipt_path)
        if receipt is None or receipt.get("schema") != RECEIPT_SCHEMA:
            excluded.append({"receipt": relative, "reason": "not_an_attempt_receipt"})
            continue
        subject = receipt.get("receipt_subject")
        row = subject.get("final_row") if isinstance(subject, dict) else None
        if not isinstance(row, dict):
            excluded.append({"receipt": relative, "reason": "no_final_row"})
            continue
        # The row inside the receipt is the row the seal was taken over, so the
        # existing verifier is the right one to ask. Writing a second check here
        # would let the two disagree about what a verified receipt means.
        if recheck_attempt_receipt(receipt_path, row) != "verified":
            excluded.append({"receipt": relative, "reason": "receipt_drift"})
            continue
        rows.append(row)
    if not rows:
        raise ValueError(f"no verifiable attempt receipt under {root}")
    return {"schema": SCHEMA, "rows": rows, "source_tree_state": run_tree_state(root),
            "rebuilt_from": {"run_root": root.as_posix(), "receipts_found": len(rows) + len(excluded),
                             "receipts_verified": len(rows), "excluded": excluded},
            "does_not_prove": DOES_NOT_PROVE}
