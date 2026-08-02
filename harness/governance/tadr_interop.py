"""tadr_interop.py -- map TADR classifications onto the organ-bundle spine.

Mirrors lesson_interop.py: produces 7-field organ-bundle entries for TADR
classification receipts, so they compose into cross-tool proof bundles.
"""
from __future__ import annotations

from typing import Any

ORGAN = "flywheel"


def classification_entry(
    receipt: dict[str, Any],
    *,
    entry_id: str = "tadr-classification-1",
    payload_ref: str = "flywheel://tadr/classification",
    trusted_authority_verdict: str = "UNVERIFIABLE",
) -> dict[str, Any]:
    """Map a sealed TADR classification receipt to a spine entry."""
    from .tadr_receipt import MATCH, verify_classification_receipt

    seal_hash = receipt.get("seal_hash", "")
    if (not isinstance(seal_hash, str) or len(seal_hash) != 64
            or seal_hash == "0" * 64):
        raise ValueError("classification receipt requires a nonzero seal")
    body = receipt.get("seal_body", {})
    tier = body.get("tier", "unknown")
    system_id = body.get("system_id", "unknown")
    status = receipt.get("status", "draft")

    structural = verify_classification_receipt(receipt)
    trusted = trusted_authority_verdict == MATCH
    if structural.get("verdict") != MATCH:
        spine_status = "unverified"
    elif status in {"approved", "active"} and trusted:
        spine_status = "pass"
    elif status == "paused" and trusted:
        spine_status = "needs-human"
    elif status == "retired" and trusted:
        spine_status = "not-applicable"
    else:
        spine_status = "unverified"

    summary = f"tier {tier} for {system_id} [{status}]"[:160]
    return {
        "entry_id": entry_id,
        "organ_id": ORGAN,
        "receipt_kind": "tadr-classification",
        "status": spine_status,
        "payload_sha256": seal_hash,
        "summary": summary,
        "payload_ref": payload_ref,
    }


def control_entry(
    receipt: dict[str, Any],
    *,
    entry_id: str = "tadr-control-1",
    payload_ref: str = "flywheel://tadr/control",
) -> dict[str, Any]:
    """Map a verified, sealed control receipt to a spine entry."""
    from .tadr_receipt import MATCH, verify_control_receipt

    seal_hash = receipt.get("seal_hash", "")
    if (not isinstance(seal_hash, str) or len(seal_hash) != 64
            or seal_hash == "0" * 64):
        raise ValueError("control receipt requires a nonzero seal")
    body = receipt.get("seal_body", {})
    tier = body.get("tier", "unknown")
    verification = verify_control_receipt(receipt)
    if verification.get("verdict") != MATCH:
        status = "unverified"
    elif body.get("compliant") is True:
        status = "pass"
    elif body.get("absent", 0) > 0:
        status = "needs-human"
    else:
        status = "unverified"
    summary = (
        f"tier {tier} controls: {body.get('present', 0)}/"
        f"{body.get('required', 0)} present"
    )
    return {
        "entry_id": entry_id,
        "organ_id": ORGAN,
        "receipt_kind": "tadr-control",
        "status": status,
        "payload_sha256": seal_hash,
        "summary": summary[:160],
        "payload_ref": payload_ref,
    }
