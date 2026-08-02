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
) -> dict[str, Any]:
    """Map a sealed TADR classification receipt to a spine entry."""
    seal_hash = receipt.get("seal_hash", "")
    body = receipt.get("seal_body", {})
    tier = body.get("tier", "unknown")
    system_id = body.get("system_id", "unknown")
    status = receipt.get("status", "draft")

    status_map = {
        "draft": "unverified", "approved": "pass", "active": "pass",
        "paused": "needs-human", "retired": "not-applicable",
    }
    spine_status = status_map.get(status, "unknown")

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
    report: dict[str, Any],
    *,
    entry_id: str = "tadr-control-1",
    payload_ref: str = "flywheel://tadr/control",
    seal_hash: str = "",
) -> dict[str, Any]:
    """Map a control compliance report to a spine entry."""
    tier = report.get("tier", "unknown")
    compliant = report.get("compliant", False)
    failed = report.get("failed", 0)

    status = "pass" if compliant else ("needs-human" if failed > 0 else "unverified")
    summary = f"tier {tier} controls: {report.get('passed',0)}/{report.get('checked',0)} pass"
    return {
        "entry_id": entry_id,
        "organ_id": ORGAN,
        "receipt_kind": "tadr-control",
        "status": status,
        "payload_sha256": seal_hash or "0" * 64,
        "summary": summary[:160],
        "payload_ref": payload_ref,
    }
