"""lesson_store.py -- the durable, append-only, cross-operator lesson memory.

The store is the layer above audit: it holds the lessons the organization
remembers, hash-chained and re-verifiable. It is NOT a per-operator tutor (that
is learn's lane); it is the cross-operator, cross-session memory that turns
surfaced drift / rollback / misconception events into lessons that compound.

Discipline:
  - Append-only. Lessons enter with status "surfaced"; transitions
    (surfaced -> admitted -> applied -> retired) are journaled as new rows, not
    in-place mutations, so the chain stays walkable.
  - Hash-chained. Each lesson's prev_hash links to the prior lesson's seal_hash.
    verify() re-walks the whole chain via verify_lesson_chain.
  - Patterns are derived, not stored. patterns() groups lessons by
    (source_organ, normalized claim) and returns Pattern records where
    repetition_count >= threshold, each carrying an improvement_candidate
    string in the same shape as telemetry.efficiency_feed, so the feedback edge
    lands in the existing admission pipeline (loop_ledger contract: surfaced for
    human admission, never autonomously applied).

Standard library only.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .lesson import (
    GENESIS_HASH,
    MATCH,
    STATUS_SURFACED,
    build_lesson,
    derive_confidence,
    verify_lesson_chain,
)

# Default: a pattern needs at least 2 converging lessons to surface.
DEFAULT_PATTERN_THRESHOLD = 2


@dataclass
class Pattern:
    """A recurring lesson: multiple lessons converging on the same claim.

    A Pattern is the feedback-edge primitive. It does not store new information;
    it aggregates existing lessons whose normalized claims match, lifts their
    confidence, and derives an improvement_candidate for human admission.
    """

    source_organ: str
    claim_normalized: str
    lesson_ids: list[str]
    repetition_count: int
    confidence: str
    improvement_candidate: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_organ": self.source_organ,
            "claim_normalized": self.claim_normalized,
            "lesson_ids": list(self.lesson_ids),
            "repetition_count": self.repetition_count,
            "confidence": self.confidence,
            "improvement_candidate": self.improvement_candidate,
        }


def _normalize_claim(claim: str) -> str:
    """Normalize a claim for pattern grouping: lowercase, collapse whitespace.

    Pattern detection groups lessons whose claims are textually similar. This is
    a deliberately simple exact-normalized grouping (the plan defers semantic
    clustering to follow-ups). Two claims group together iff their normalized
    forms are identical.
    """
    return re.sub(r"\s+", " ", claim.strip().lower())


class LessonStore:
    """An append-only, hash-chained store of organizational lessons.

    Persistence is canonical JSON lines: one lesson per line (compact JSON,
    UTF-8). The file is the chain; load() re-reads it into memory. The store
    never holds raw evidence payloads, only the digests each lesson's seal body
    already carries.
    """

    def __init__(self) -> None:
        self._lessons: list[dict[str, Any]] = []

    @property
    def lessons(self) -> list[dict[str, Any]]:
        return list(self._lessons)

    def __len__(self) -> int:
        return len(self._lessons)

    # --- append --------------------------------------------------------

    def append(self, lesson: dict[str, Any]) -> dict[str, Any]:
        """Append a sealed lesson to the chain.

        The lesson's seq and prev_hash are set by the store (the store owns the
        chain order); the lesson_id and seal_hash stay as built (they bind the
        content). Returns the lesson as appended (with corrected seq/prev_hash).
        Raises ValueError if the lesson does not verify on its own.
        """
        # The lesson must seal-verify on its own before entering the chain.
        from .lesson import verify_lesson

        v = verify_lesson(lesson)
        if v["verdict"] != MATCH:
            raise ValueError(f"cannot append a lesson that does not verify: {v}")

        prev = self._lessons[-1]["seal_hash"] if self._lessons else GENESIS_HASH
        lesson["seq"] = len(self._lessons)
        lesson["prev_hash"] = prev
        self._lessons.append(lesson)
        return lesson

    def append_built(self, **kwargs: Any) -> dict[str, Any]:
        """Build a lesson and append it in one call.

        Convenience for mappers: build_lesson(**kwargs) then append(). The store
        sets seq and prev_hash.
        """
        lesson = build_lesson(**kwargs)
        return self.append(lesson)

    # --- queries -------------------------------------------------------

    def by_source_organ(self, organ: str) -> list[dict[str, Any]]:
        return [l for l in self._lessons if l.get("seal_body", {}).get("source_organ") == organ]

    def by_kind(self, kind: str) -> list[dict[str, Any]]:
        return [l for l in self._lessons if l.get("seal_body", {}).get("kind") == kind]

    def by_status(self, status: str) -> list[dict[str, Any]]:
        return [l for l in self._lessons if l.get("status") == status]

    # --- the feedback edge --------------------------------------------

    def patterns(self, threshold: int = DEFAULT_PATTERN_THRESHOLD) -> list[Pattern]:
        """Detect recurring lesson patterns for human admission.

        Groups lessons by (source_organ, normalized_claim) and returns Pattern
        records where the group size >= threshold. A single instance does not
        auto-promote to a pattern. Each Pattern carries an improvement_candidate
        string in the same shape as telemetry.efficiency_feed, so it feeds the
        existing admission pipeline.
        """
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for lesson in self._lessons:
            body = lesson.get("seal_body", {})
            key = (body.get("source_organ", ""), _normalize_claim(body.get("claim", "")))
            groups.setdefault(key, []).append(lesson)

        patterns: list[Pattern] = []
        for (organ, claim_norm), group in groups.items():
            if len(group) < threshold:
                continue
            # Aggregate confidence: cross-organ convergence lifts the floor.
            confidence = derive_confidence("repeated", len(group))
            lesson_ids = [l.get("lesson_id", "") for l in group]
            # The improvement_candidate is the surfaced claim, attributed to its
            # source organ, for human admission. It is a suggestion, never an
            # applied change.
            improvement_candidate = (
                f"{len(group)} lessons from {organ} converge on: "
                f"{group[0].get('seal_body', {}).get('claim', '')} "
                f"(review for systemic cause)"
            )
            patterns.append(
                Pattern(
                    source_organ=organ,
                    claim_normalized=claim_norm,
                    lesson_ids=lesson_ids,
                    repetition_count=len(group),
                    confidence=confidence,
                    improvement_candidate=improvement_candidate,
                )
            )
        # Most-converging first (highest-leverage pattern surfaces first).
        patterns.sort(key=lambda p: p.repetition_count, reverse=True)
        return patterns

    def improvement_feed(self, threshold: int = DEFAULT_PATTERN_THRESHOLD) -> dict[str, Any]:
        """The feed-back artifact: lesson patterns as improvement_candidates.

        Same shape as telemetry.efficiency_feed so the learning loop and the
        efficiency loop feed one admission pipeline. improvement_candidates is a
        list[str], each a surfaced pattern for human review.
        """
        pats = self.patterns(threshold=threshold)
        return {
            "improvement_candidates": [p.improvement_candidate for p in pats],
            "profile": {
                "n_lessons": len(self._lessons),
                "n_patterns": len(pats),
                "n_source_organs": len(
                    {l.get("seal_body", {}).get("source_organ", "") for l in self._lessons}
                ),
            },
            "feed_summary": (
                f"{len(pats)} recurring patterns from {len(self._lessons)} lessons "
                f"({len(self.by_status(STATUS_SURFACED))} surfaced for admission)"
            ),
        }

    # --- verify --------------------------------------------------------

    def verify(self) -> dict[str, Any]:
        """Re-walk the whole chain. MATCH only if every lesson + linkage holds."""
        return verify_lesson_chain(self._lessons)

    # --- persistence ---------------------------------------------------

    def save(self, path: Path) -> Path:
        """Write the chain as canonical JSON lines (one lesson per line)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(l, separators=(",", ":"), ensure_ascii=False) for l in self._lessons
        ]
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "LessonStore":
        """Load a store from a JSON-lines file. Empty file yields an empty store."""
        path = Path(path)
        store = cls()
        if not path.exists():
            return store
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            store._lessons.append(json.loads(line))
        return store
