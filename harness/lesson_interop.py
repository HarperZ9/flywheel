"""lesson_interop.py -- map lessons onto the shared organ-bundle spine.

Mirrors learn's interop.mjs exactly: the same 7-field entry shape, the same
status vocabulary, the same digest-only discipline. A lesson becomes a spine
entry so it composes into a cross-tool proof bundle alongside crucible
assessments, gather corpora, forum routes, index envelopes, and learn receipts.

Entry shape (matches the proof-surface organ-bundle contract):
  (entry_id, organ_id, receipt_kind, status, payload_sha256, summary, payload_ref)

organ_id is "flywheel"; receipt_kind is "learn-lesson" (added to proof-surface's
closed RECEIPT_KINDS set). payload_sha256 is the lesson's seal_hash (the
content-addressed identity of its seal body). payload_ref is a stable pointer
at the lesson in its store.

Standard library only.
"""
from __future__ import annotations

import json
from typing import Any

from .lesson import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MODERATE,
    STATUS_ADMITTED,
    STATUS_APPLIED,
    STATUS_RETIRED,
    STATUS_SURFACED,
)

ORGAN = "flywheel"
SPINE_KIND = "learn-lesson"

# The spine status vocabulary (matches learn's interop.mjs STATUSES set).
STATUSES = frozenset(
    {"pass", "fail", "unverified", "warn", "needs-human", "not-applicable", "unknown"}
)

_HEX64 = frozenset("0123456789abcdef")


def _is_hex64(s: str) -> bool:
    return bool(s) and len(s) == 64 and all(c in set("0123456789abcdef") for c in s)


def _lesson_to_spine_status(lesson: dict[str, Any]) -> str:
    """Map a lesson's lifecycle status + confidence to a spine status.

    surfaced -> needs-human (the lesson is awaiting admission)
    admitted -> pass (a human accepted it as worth acting on)
    applied  -> pass (the lesson drove a change)
    retired  -> not-applicable (no longer active)
    Low-confidence surfaced -> unverified (weaker claim, flagged for review).
    """
    status = lesson.get("status", STATUS_SURFACED)
    confidence = lesson.get("seal_body", {}).get("confidence", CONFIDENCE_LOW)

    if status == STATUS_SURFACED:
        if confidence == CONFIDENCE_LOW:
            return "unverified"
        return "needs-human"
    if status == STATUS_ADMITTED:
        return "pass"
    if status == STATUS_APPLIED:
        return "pass"
    if status == STATUS_RETIRED:
        return "not-applicable"
    return "unknown"


def lesson_entry(
    lesson: dict[str, Any],
    *,
    entry_id: str = "learn-lesson-1",
    payload_ref: str = "flywheel://lesson",
) -> dict[str, Any]:
    """Map a sealed lesson to an organ-bundle spine entry.

    payload_sha256 is the lesson's seal_hash (content-addressed). The summary
    is a one-line, 160-char-capped description for a reviewer scanning a bundle.
    """
    seal_hash = lesson.get("seal_hash", "")
    body = lesson.get("seal_body", {})
    kind = body.get("kind", "unknown")
    organ = body.get("source_organ", "unknown")
    claim = body.get("claim", "")
    confidence = body.get("confidence", "unknown")
    status = lesson.get("status", STATUS_SURFACED)

    summary = f"{kind} from {organ}: {claim} [{confidence}, {status}]"[:160]
    return {
        "entry_id": entry_id,
        "organ_id": ORGAN,
        "receipt_kind": SPINE_KIND,
        "status": _lesson_to_spine_status(lesson),
        "payload_sha256": seal_hash,
        "summary": summary,
        "payload_ref": payload_ref,
    }


def validate_lesson_entry(entry: dict[str, Any]) -> bool:
    """Validate a lesson spine entry against the organ-bundle contract.

    Same invariants learn's interop.mjs enforces: exactly the 7 fields, the
    correct organ_id and receipt_kind, a valid status, and a 64-char hex digest.
    """
    if not isinstance(entry, dict):
        return False
    fields = [
        "entry_id",
        "organ_id",
        "receipt_kind",
        "status",
        "payload_sha256",
        "summary",
        "payload_ref",
    ]
    if sorted(entry.keys()) != sorted(fields):
        return False
    if entry["organ_id"] != ORGAN:
        return False
    if entry["receipt_kind"] != SPINE_KIND:
        return False
    if entry["status"] not in STATUSES:
        return False
    if not _is_hex64(entry["payload_sha256"]):
        return False
    return True


def lesson_bundle(
    lessons: list[dict[str, Any]],
    *,
    bundle_id: str = "lesson-bundle",
    subject: str = "organizational-learning-loop",
    generated_at: str = "",
) -> dict[str, Any]:
    """Build a full organ-receipt-bundle from a list of lessons.

    The bundle is a reviewer/tool handoff contract: it ties lesson spine entries
    together by digest and reference, with edges showing derivation. It carries
    no heavy payloads and grants no authority (same discipline as every other
    organ bundle). Validated by proof-surface's validate_organ_receipt_bundle.
    """
    entries = [
        lesson_entry(lesson, entry_id=f"learn-lesson-{i}")
        for i, lesson in enumerate(lessons)
    ]
    edges = []
    for i in range(1, len(entries)):
        edges.append(
            {"from": entries[i - 1]["entry_id"], "to": entries[i]["entry_id"], "relation": "observed-after"}
        )
    return {
        "organ_bundle_version": "0.1",
        "bundle_id": bundle_id,
        "generated_at": generated_at,
        "subject": subject,
        "entries": entries,
        "edges": edges,
        "notes": "Organizational learning loop: lesson spine entries, digests only.",
    }
