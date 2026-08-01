"""lesson_mappers.py -- derive lessons from witnessed artifacts across flagships.

A mapper reads a flagship's witnessed output and derives a Lesson when the
output shows a divergence worth remembering. The first mapper proven
end-to-end is the intent-vs-outcome mapper: it reads accountable-surface's
ActuationOutcome (the per-action intent-vs-outcome record) and derives a lesson
when an allowed action failed or rolled back.

The mapper is an adapter, not a coupling. It reads the ActuationOutcome shape
(dict projection); if that shape shifts, the mapper's projection shifts with
it. The mapper never imports accountable-surface; it consumes the dict any
serialization of ActuationOutcome produces.

Design:
  - Only divergences become lessons. A clean run (verdict == pass, no rollback)
    produces zero lessons. This is the honest null: the absence of a lesson is
    meaningful, not a gap.
  - Each lesson's source_refs carry the outcome's after_digest (the witnessed
    effect), never the raw outcome payload.
  - rationale is projected from the outcome's grounding when present (stated
    intent + confidence), null otherwise. Never fabricated.
  - evidence_class is single-instance (one action); confidence is low by
    default. The pattern detector lifts confidence when lessons recur.

Standard library only.
"""
from __future__ import annotations

from typing import Any

from .lesson import (
    EVIDENCE_SINGLE,
    KIND_INTENT_OUTCOME,
    build_lesson,
)

SOURCE_ORGAN = "accountable-surface"

# Well-formed sha256 hex (the digest fields on ActuationOutcome).
_HE64 = frozenset("0123456789abcdefABCDEF")


def _is_hex64(s: str) -> bool:
    return bool(s) and len(s) == 64 and all(c in _HE64 for c in s)


def _is_divergence(outcome: dict[str, Any]) -> bool:
    """An intent-vs-outcome divergence: the gate allowed it, but the verified
    effect did not match the intent, or the action was rolled back.

    decision == "allow" + (verdict == "failed" OR rolled_back == True).
    A denied or needs-human action is NOT a divergence (the gate did its job).
    """
    if outcome.get("decision") != "allow":
        return False
    if outcome.get("verdict") == "failed":
        return True
    if outcome.get("rolled_back") is True:
        return True
    return False


def _project_rationale(outcome: dict[str, Any]) -> dict[str, Any] | None:
    """Project the outcome's grounding into the typed rationale block.

    Grounding carries {subject, references, confidence, digest}. We project
    subject -> stated_intent and confidence -> confidence. If there is no
    grounding, or it lacks a subject, the rationale is None (honest null).
    """
    grounding = outcome.get("grounding")
    if not isinstance(grounding, dict):
        return None
    subject = grounding.get("subject")
    if not subject:
        return None
    confidence = grounding.get("confidence", "unknown")
    return {
        "stated_intent": str(subject),
        "options_considered": [],  # accountable-surface does not record alternatives today
        "chosen_option": "actuate",  # the surface chose to act; that is the recorded choice
        "confidence": str(confidence),
    }


def _source_ref(outcome: dict[str, Any]) -> dict[str, str] | None:
    """The witnessed artifact ref for this lesson: the after_digest.

    If after_digest is absent or malformed, fall back to before_digest. If both
    are absent, return None (the caller skips this outcome: a lesson with no
    witnessed digest is unverifiable by construction).
    """
    for field in ("after_digest", "before_digest"):
        digest = outcome.get(field)
        if _is_hex64(digest):
            return {
                "organ": SOURCE_ORGAN,
                "ref": f"actuation:{outcome.get('certificate', {}).get('certificate_id', 'unknown')}",
                "digest": digest,
            }
    return None


def _claim_from_reasons(outcome: dict[str, Any]) -> str:
    """Derive the lesson claim from the gate's own typed failure reasons.

    The reasons are the surface's own explanation of why the verified effect did
    not match the intent. We join them into one sentence. If there are no
    reasons, we use a typed default that names the divergence class.
    """
    reasons = outcome.get("reasons") or []
    reasons = [str(r) for r in reasons if r]
    if reasons:
        return "allowed action diverged: " + "; ".join(reasons)
    if outcome.get("rolled_back") is True:
        return "allowed action rolled back (intent did not hold under contact)"
    return "allowed action failed verification"


def intent_outcome_lessons(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive lessons from a list of accountable-surface ActuationOutcome dicts.

    Only divergences (allowed but failed / rolled back) become lessons. A clean
    run produces zero lessons. Each lesson is built (sealed) but NOT appended to
    a store; the caller decides where the lesson lands.
    """
    lessons: list[dict[str, Any]] = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        if not _is_divergence(outcome):
            continue
        ref = _source_ref(outcome)
        if ref is None:
            # A lesson with no witnessed digest is unverifiable; skip honestly.
            continue
        lesson = build_lesson(
            kind=KIND_INTENT_OUTCOME,
            source_organ=SOURCE_ORGAN,
            source_refs=[ref],
            claim=_claim_from_reasons(outcome),
            evidence_class=EVIDENCE_SINGLE,
            repetition_count=1,
            scope="single action; does not prove a systemic pattern",
            rationale=_project_rationale(outcome),
        )
        lessons.append(lesson)
    return lessons


def append_intent_outcome_lessons(
    store: Any, outcomes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Derive and append intent-outcome lessons to a LessonStore in one call.

    Returns the lessons that were appended (empty list for a clean run).
    """
    lessons = intent_outcome_lessons(outcomes)
    for lesson in lessons:
        store.append(lesson)
    return lessons
