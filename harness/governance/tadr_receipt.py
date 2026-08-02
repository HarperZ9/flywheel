"""tadr_receipt.py -- sealed receipt for a TADR tier classification.

Analog of harness/lesson.py: a sealed, content-addressed record that binds a
tier classification to its evidence. The classification is an authorization
decision (asserted by an accountable authority), so it is sealed, not derived.

Schema: flywheel.tadr-classification/v1.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA = "flywheel.tadr-classification/v1"

TIER_STATUSES = frozenset({"draft", "approved", "active", "paused", "retired"})

_HEX64 = frozenset("0123456789abcdefABCDEF")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _digest_well_formed(s: str) -> bool:
    return bool(s) and len(s) == 64 and all(c in _HEX64 for c in s)


def build_classification_receipt(
    *,
    tier: str,
    modifiers: list[str],
    system_id: str,
    consequence_analysis: str,
    evidence_quality: str = "moderate",
    uncertainty: str = "moderate",
    residual_risk: str = "",
    approving_authorities: list[str] | None = None,
    dissent: str = "",
    pause_triggers: list[str] | None = None,
    review_date: str = "",
    status: str = "draft",
) -> dict[str, Any]:
    """Build a sealed TADR classification receipt."""
    from .tadr_tier import validate_tier, validate_modifiers
    if not validate_tier(tier):
        raise ValueError(f"invalid tier: {tier!r}")
    invalid = validate_modifiers(modifiers)
    if invalid:
        raise ValueError(f"invalid modifiers: {invalid}")
    if status not in TIER_STATUSES:
        raise ValueError(f"invalid status: {status!r}")

    seal_body = {
        "tier": tier,
        "modifiers": list(modifiers),
        "system_id": system_id,
        "consequence_analysis": consequence_analysis,
        "evidence_quality": evidence_quality,
        "uncertainty": uncertainty,
        "residual_risk": residual_risk,
        "approving_authorities": list(approving_authorities or []),
        "dissent": dissent,
        "pause_triggers": list(pause_triggers or []),
        "review_date": review_date,
    }
    seal_hash = _sha256_hex(_canonical_bytes(seal_body))
    return {
        "schema": SCHEMA,
        "classification_id": seal_hash,
        "seal_hash": seal_hash,
        "seal_body": seal_body,
        "status": status,
        "created_at": _utc_now(),
    }


MATCH = "MATCH"
TAMPERED = "TAMPERED"
UNVERIFIABLE = "UNVERIFIABLE"


def verify_classification_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Verify a TADR classification receipt's seal and structure."""
    if not isinstance(receipt, dict):
        return {"verdict": UNVERIFIABLE, "detail": "not an object"}
    if receipt.get("schema") != SCHEMA:
        return {"verdict": UNVERIFIABLE, "detail": "schema mismatch"}

    seal_hash = receipt.get("seal_hash", "")
    if not _digest_well_formed(seal_hash):
        return {"verdict": UNVERIFIABLE, "detail": "seal_hash not hex64"}

    seal_body = receipt.get("seal_body")
    if not isinstance(seal_body, dict):
        return {"verdict": UNVERIFIABLE, "detail": "no seal_body"}

    recomputed = _sha256_hex(_canonical_bytes(seal_body))
    if recomputed != seal_hash:
        return {"verdict": TAMPERED, "detail": "seal mismatch"}

    if receipt.get("classification_id") != seal_hash:
        return {"verdict": UNVERIFIABLE, "detail": "classification_id != seal_hash"}

    from .tadr_tier import validate_tier
    if not validate_tier(seal_body.get("tier", "")):
        return {"verdict": UNVERIFIABLE, "detail": "invalid tier in seal_body"}

    status = receipt.get("status", "")
    if status not in TIER_STATUSES:
        return {"verdict": UNVERIFIABLE, "detail": f"invalid status: {status!r}"}

    return {"verdict": MATCH, "tier": seal_body.get("tier"),
            "status": status}
