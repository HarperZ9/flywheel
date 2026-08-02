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
    STATUS_ADMITTED,
    STATUS_APPLIED,
    STATUS_RETIRED,
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
    weight: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_organ": self.source_organ,
            "claim_normalized": self.claim_normalized,
            "lesson_ids": list(self.lesson_ids),
            "repetition_count": self.repetition_count,
            "confidence": self.confidence,
            "improvement_candidate": self.improvement_candidate,
            "weight": round(self.weight, 3) if self.weight else 0.0,
        }


def _normalize_claim(claim: str) -> str:
    """Normalize a claim for pattern grouping: lowercase, collapse whitespace.

    Pattern detection groups lessons whose claims are textually similar. This is
    a deliberately simple exact-normalized grouping (the plan defers semantic
    clustering to follow-ups). Two claims group together iff their normalized
    forms are identical.
    """
    return re.sub(r"\s+", " ", claim.strip().lower())


def _tokenize(claim: str) -> frozenset[str]:
    """Tokenize a claim for semantic similarity: lowercase word-boundary tokens.

    Drops tokens shorter than 3 characters (a, an, the, of, etc.) so the Jaccard
    over token sets measures content-word overlap, not stopword coincidence.
    """
    return frozenset(t for t in re.findall(r"[a-z0-9]+", claim.lower()) if len(t) >= 3)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity over two token sets: |intersection| / |union|.

    Returns 0.0 if both sets are empty (two empty claims are NOT similar).
    """
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


# Default thresholds for the opt-in detection modes.
DEFAULT_SEMANTIC_THRESHOLD = 0.5
DEFAULT_TEMPORAL_HALFLIFE_DAYS = 30
DEFAULT_TEMPORAL_CUTOFF_DAYS = 90


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

    # --- transitions (append-only journal) ----------------------------

    # Allowed status transitions. A retired lesson is terminal.
    _ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
        STATUS_SURFACED: frozenset({STATUS_ADMITTED, STATUS_RETIRED}),
        STATUS_ADMITTED: frozenset({STATUS_APPLIED, STATUS_RETIRED}),
        STATUS_APPLIED: frozenset({STATUS_RETIRED}),
        STATUS_RETIRED: frozenset(),  # terminal
    }

    def latest_for(self, lesson_id: str) -> dict[str, Any] | None:
        """Return the most recent row for a content-addressed lesson_id.

        Since transitions append new rows with the same lesson_id (same
        seal_hash), this finds the last one in chain order, which carries the
        current status.
        """
        for lesson in reversed(self._lessons):
            if lesson.get("lesson_id") == lesson_id:
                return lesson
        return None

    def transition(
        self, lesson_id: str, new_status: str,
    ) -> dict[str, Any]:
        """Append a status transition as a new row (append-only discipline).

        Finds the latest row with the given lesson_id, validates the transition
        is legal, then appends a new row with the same seal_body (identical
        content, identical lesson_id) but the new status. The chain still
        verifies because the seal_hash reproduces (the content did not change).
        Returns the new row, or raises ValueError on an illegal transition.
        """
        current = self.latest_for(lesson_id)
        if current is None:
            raise ValueError(f"no lesson with lesson_id {lesson_id[:16]}...")
        old_status = current.get("status", STATUS_SURFACED)
        allowed = self._ALLOWED_TRANSITIONS.get(old_status, frozenset())
        if new_status not in allowed:
            raise ValueError(
                f"transition {old_status} -> {new_status} not allowed "
                f"(allowed: {sorted(allowed) or 'terminal'})"
            )
        body = current.get("seal_body", {})
        new_lesson = build_lesson(
            kind=body.get("kind", "drift"),
            source_organ=body.get("source_organ", "flywheel"),
            source_refs=body.get("source_refs", []),
            claim=body.get("claim", ""),
            evidence_class=body.get("evidence_class", "single-instance"),
            repetition_count=body.get("repetition_count", 1),
            scope=body.get("scope", ""),
            rationale=body.get("rationale"),
            status=new_status,
            created_at=current.get("created_at", ""),
        )
        return self.append(new_lesson)

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
        # Most-converging first (highest-signal pattern surfaces first).
        patterns.sort(key=lambda p: p.repetition_count, reverse=True)
        return patterns

    def improvement_feed(
        self,
        threshold: int = DEFAULT_PATTERN_THRESHOLD,
        *,
        temporal: bool = False,
        now: str = "",
    ) -> dict[str, Any]:
        """The feed-back artifact: lesson patterns as improvement_candidates.

        Same shape as telemetry.efficiency_feed so the learning loop and the
        efficiency loop feed one admission pipeline. improvement_candidates is a
        list[str], each a surfaced pattern for human review.

        When temporal=True, uses decay-weighted pattern detection so recent
        activity ranks above stale patterns. The feed_summary notes the window.
        """
        if temporal:
            pats = self.patterns_temporal(now=now)
        else:
            pats = self.patterns(threshold=threshold)
        summary = (
            f"{len(pats)} recurring patterns from {len(self._lessons)} lessons "
            f"({len(self.by_status(STATUS_SURFACED))} surfaced for admission)"
        )
        if temporal:
            summary += f" [temporal decay, {DEFAULT_TEMPORAL_HALFLIFE_DAYS}d half-life]"
        return {
            "improvement_candidates": [p.improvement_candidate for p in pats],
            "profile": {
                "n_lessons": len(self._lessons),
                "n_patterns": len(pats),
                "n_source_organs": len(
                    {l.get("seal_body", {}).get("source_organ", "") for l in self._lessons}
                ),
            },
            "feed_summary": summary,
        }

    def patterns_semantic(
        self,
        *,
        threshold: float = DEFAULT_SEMANTIC_THRESHOLD,
        min_group: int = DEFAULT_PATTERN_THRESHOLD,
    ) -> list[Pattern]:
        """Semantic similarity grouping: groups claims by Jaccard token overlap.

        Catches near-match claims that exact grouping misses (e.g. "allowed
        action rolled back: target mismatch" and "allowed action rolled back:
        digest drift" share most content words). Uses union-find to merge
        transitively-similar claims into one group. A Pattern's
        claim_normalized is the most frequent original claim in the group.
        """
        # Tokenize every lesson's claim.
        tokenized = [
            (lesson, _tokenize(lesson.get("seal_body", {}).get("claim", "")))
            for lesson in self._lessons
        ]
        # Union-find over lesson indices: merge if Jaccard >= threshold.
        n = len(tokenized)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            for j in range(i + 1, n):
                if find(i) == find(j):
                    continue
                if _jaccard(tokenized[i][1], tokenized[j][1]) >= threshold:
                    union(i, j)

        # Group by root.
        groups: dict[int, list[dict[str, Any]]] = {}
        for i, (lesson, _) in enumerate(tokenized):
            groups.setdefault(find(i), []).append(lesson)

        patterns: list[Pattern] = []
        for group in groups.values():
            if len(group) < min_group:
                continue
            organs = {l.get("seal_body", {}).get("source_organ", "") for l in group}
            # Use the first lesson's organ as the representative (groups may
            # span organs if claims converge cross-tool).
            organ = group[0].get("seal_body", {}).get("source_organ", "")
            # claim_normalized: the most common original claim in the group.
            claims = [l.get("seal_body", {}).get("claim", "") for l in group]
            claim_norm = _normalize_claim(max(set(claims), key=claims.count))
            confidence = derive_confidence("repeated", len(group))
            lesson_ids = [l.get("lesson_id", "") for l in group]
            improvement_candidate = (
                f"{len(group)} lessons converge on: {claims[0]} "
                f"(review for systemic cause)"
            )
            patterns.append(Pattern(
                source_organ=organ,
                claim_normalized=claim_norm,
                lesson_ids=lesson_ids,
                repetition_count=len(group),
                confidence=confidence,
                improvement_candidate=improvement_candidate,
            ))
        patterns.sort(key=lambda p: p.repetition_count, reverse=True)
        return patterns

    def patterns_temporal(
        self,
        *,
        now: str = "",
        halflife_days: int = DEFAULT_TEMPORAL_HALFLIFE_DAYS,
        cutoff_days: int = DEFAULT_TEMPORAL_CUTOFF_DAYS,
        min_weight: float = 1.0,
    ) -> list[Pattern]:
        """Temporal decay weighting: recent lessons rank above stale ones.

        A lesson's contribution decays exponentially with age (half-life
        default 30 days). A lesson older than the cutoff (default 90 days)
        contributes weight 0. The exact-match groups from patterns() are used;
        each group's weight is the sum of its members' decay weights. Groups
        whose total weight is below min_weight (default 1.0, meaning at least
        one fresh lesson's worth of signal) are suppressed.
        """
        from datetime import datetime, timezone, timedelta

        if not now:
            now_dt = datetime.now(timezone.utc)
        else:
            now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))

        def _weight(lesson: dict[str, Any]) -> float:
            created = lesson.get("created_at", "")
            if not created:
                return 0.0
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return 0.0
            age_days = (now_dt - created_dt).total_seconds() / 86400
            if age_days < 0:
                return 1.0  # future-dated; treat as fresh
            if age_days > cutoff_days:
                return 0.0
            return 0.5 ** (age_days / halflife_days)

        # Reuse the exact-match grouping, then weight each group.
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for lesson in self._lessons:
            body = lesson.get("seal_body", {})
            key = (body.get("source_organ", ""), _normalize_claim(body.get("claim", "")))
            groups.setdefault(key, []).append(lesson)

        patterns: list[Pattern] = []
        for (organ, claim_norm), group in groups.items():
            weights = [_weight(l) for l in group]
            total_weight = sum(weights)
            if total_weight < min_weight:
                continue
            confidence = derive_confidence("repeated", len(group))
            lesson_ids = [l.get("lesson_id", "") for l in group]
            improvement_candidate = (
                f"{len(group)} lessons from {organ} (weight {total_weight:.1f}): "
                f"{group[0].get('seal_body', {}).get('claim', '')} "
                f"(review for systemic cause)"
            )
            patterns.append(Pattern(
                source_organ=organ,
                claim_normalized=claim_norm,
                lesson_ids=lesson_ids,
                repetition_count=len(group),
                confidence=confidence,
                improvement_candidate=improvement_candidate,
                weight=total_weight,
            ))
        # Sort by weight (highest-signal recent pattern first).
        patterns.sort(key=lambda p: p.weight, reverse=True)
        return patterns

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
