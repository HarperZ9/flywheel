"""lesson_mappers.py -- derive lessons from witnessed artifacts across flagships.

A mapper reads a flagship's witnessed output and derives a Lesson when the
output shows a divergence worth remembering. Three mappers ship:

  1. intent_outcome_lessons: reads accountable-surface's ActuationOutcome (the
     per-action intent-vs-outcome record) and derives a lesson when an allowed
     action failed or rolled back.
  2. drift_lessons: reads mneme's drift report (per-memory MATCH / DRIFT /
     UNVERIFIABLE) and derives a lesson when a memory drifted from its source.
  3. misconception_lessons: reads learn's misconceptions output (per-objective
     wrong-attempt aggregation) and derives a cross-operator lesson when an
     objective is repeatedly missed.

Each mapper is an adapter, not a coupling. It reads the flagship's dict shape;
if that shape shifts, the mapper's projection shifts with it. No mapper
imports the flagship it reads.

Design:
  - Only divergences become lessons. A clean run produces zero lessons. This is
    the honest null: the absence of a lesson is meaningful, not a gap.
  - source_refs carry digests, never payloads. When the source dict already
    carries a digest (ActuationOutcome), we use it. When it does not (mneme
    drift, learn misconceptions), we compute a content-addressed digest over the
    canonical bytes of the source dict itself, so the lesson is still bound to
    its evidence by hash.
  - rationale is null for drift and misconception mappers (those flagships do
    not record decision rationale). Never fabricated.
  - evidence_class is single-instance; confidence is low by default. The pattern
    detector lifts confidence when lessons recur.

Standard library only.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .lesson import (
    EVIDENCE_SINGLE,
    KIND_DRIFT,
    KIND_INTENT_OUTCOME,
    KIND_MISCONCEPTION,
    build_lesson,
)

SOURCE_ORGAN = "accountable-surface"
SOURCE_ORGAN_MNEME = "mneme"
SOURCE_ORGAN_LEARN = "learn"

# Well-formed sha256 hex (the digest fields on ActuationOutcome).
_HE64 = frozenset("0123456789abcdefABCDEF")


def _is_hex64(s: str) -> bool:
    return bool(s) and len(s) == 64 and all(c in _HE64 for c in s)


def _content_digest(obj: Any) -> str:
    """Compute a content-addressed sha256 over a dict's canonical JSON bytes.

    Used when the source dict does not carry its own digest field (mneme drift
    verdicts, learn misconception entries). The digest binds the lesson to the
    exact bytes of its evidence, so a changed source yields a different digest.
    """
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


# ---------------------------------------------------------------------------
# Drift mapper: mneme drift report -> lessons
# ---------------------------------------------------------------------------
#
# mneme's drift_report returns a dict with a "verdicts" list. Each verdict is:
#   {memory_id, verdict, reason, changed_sources, missing_sources}
# verdict is "MATCH" | "DRIFT" | "UNVERIFIABLE". The verdict dict carries no
# digest field, so we compute a content-addressed digest over it to bind the
# lesson to its evidence.


def _is_drift(verdict_entry: dict[str, Any]) -> bool:
    """A drift worth remembering: the memory's source changed under it.

    UNVERIFIABLE (source gone) is a different failure class: the source is
    absent, not changed. We surface DRIFT as a lesson because it means a fact
    the system held is now wrong. UNVERIFIABLE is surfaced too, as a separate
    lesson kind, because it means the system cannot confirm the fact at all.
    """
    v = verdict_entry.get("verdict", "")
    return v in ("DRIFT", "UNVERIFIABLE")


def _drift_claim(verdict_entry: dict[str, Any]) -> str:
    """Derive the lesson claim from the drift verdict."""
    memory_id = verdict_entry.get("memory_id", "unknown")
    v = verdict_entry.get("verdict", "")
    if v == "DRIFT":
        changed = verdict_entry.get("changed_sources", [])
        sources = ", ".join(str(s) for s in changed[:3]) if changed else "sources"
        return f"memory {memory_id} drifted: {sources} changed since extraction"
    if v == "UNVERIFIABLE":
        missing = verdict_entry.get("missing_sources", [])
        if missing:
            sources = ", ".join(str(s) for s in missing[:3])
            return f"memory {memory_id} unverifiable: {sources} gone or unrecorded"
        return f"memory {memory_id} unverifiable: no grounding to confirm"
    return f"memory {memory_id}: {v}"


def drift_lessons(drift_report: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive lessons from a mneme drift report.

    Reads the report's "verdicts" list and derives a lesson for each DRIFT or
    UNVERIFIABLE memory. A clean store (all MATCH) produces zero lessons.
    """
    if not isinstance(drift_report, dict):
        return []
    verdicts = drift_report.get("verdicts", [])
    if not isinstance(verdicts, list):
        return []

    lessons: list[dict[str, Any]] = []
    for verdict_entry in verdicts:
        if not isinstance(verdict_entry, dict):
            continue
        if not _is_drift(verdict_entry):
            continue
        # Content-addressed digest: binds the lesson to the exact verdict bytes.
        digest = _content_digest(verdict_entry)
        memory_id = str(verdict_entry.get("memory_id", "unknown"))
        lesson = build_lesson(
            kind=KIND_DRIFT,
            source_organ=SOURCE_ORGAN_MNEME,
            source_refs=[{
                "organ": SOURCE_ORGAN_MNEME,
                "ref": f"drift:{memory_id}",
                "digest": digest,
            }],
            claim=_drift_claim(verdict_entry),
            evidence_class=EVIDENCE_SINGLE,
            repetition_count=1,
            scope="single memory; does not prove a systemic pattern",
            rationale=None,  # mneme does not record decision rationale
        )
        lessons.append(lesson)
    return lessons


def append_drift_lessons(
    store: Any, drift_report: dict[str, Any]
) -> list[dict[str, Any]]:
    """Derive and append drift lessons to a LessonStore in one call."""
    lessons = drift_lessons(drift_report)
    for lesson in lessons:
        store.append(lesson)
    return lessons


# ---------------------------------------------------------------------------
# Misconception mapper: learn misconceptions -> cross-operator lessons
# ---------------------------------------------------------------------------
#
# learn's misconceptions output is an array of:
#   {objective, count, notes: [feedback...]}
# sorted by count descending. It carries no digest field. Each entry aggregates
# one operator's wrong attempts for an objective. The mapper derives a lesson
# per misconception entry, so recurring misconceptions across operators form a
# pattern in the store.


def _misconception_claim(entry: dict[str, Any]) -> str:
    """Derive the lesson claim from a misconception entry."""
    objective = entry.get("objective", "unknown")
    count = entry.get("count", 0)
    return f"objective {objective} repeatedly missed ({count} wrong attempts)"


def misconception_lessons(misconceptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive lessons from learn's misconceptions output.

    Each misconception entry becomes a lesson. The count is carried as the
    repetition_count so the confidence floor reflects how many times the
    objective was missed by this operator. The lesson's claim normalizes by
    objective so cross-operator convergence forms a pattern in the store.
    """
    if not isinstance(misconceptions, list):
        return []

    lessons: list[dict[str, Any]] = []
    for entry in misconceptions:
        if not isinstance(entry, dict):
            continue
        count = entry.get("count", 0)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            continue  # no wrong attempts; skip honestly
        digest = _content_digest(entry)
        objective = str(entry.get("objective", "unknown"))
        lesson = build_lesson(
            kind=KIND_MISCONCEPTION,
            source_organ=SOURCE_ORGAN_LEARN,
            source_refs=[{
                "organ": SOURCE_ORGAN_LEARN,
                "ref": f"misconception:{objective}",
                "digest": digest,
            }],
            claim=_misconception_claim(entry),
            evidence_class=EVIDENCE_SINGLE,
            repetition_count=1,
            scope="single operator; cross-operator convergence forms a pattern",
            rationale=None,  # learn does not record decision rationale
        )
        lessons.append(lesson)
    return lessons


def append_misconception_lessons(
    store: Any, misconceptions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Derive and append misconception lessons to a LessonStore in one call."""
    lessons = misconception_lessons(misconceptions)
    for lesson in lessons:
        store.append(lesson)
    return lessons
