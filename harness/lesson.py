"""lesson.py -- the sealed, hash-chained record of an organizational lesson.

The layer above audit. A lesson is not a free-text note an operator wrote; it is
a claim derived from witnessed artifacts (a drift, a rollback, a graded failure),
bound by hash to its evidence, re-checkable offline, and fail-closed when the
evidence is gone. The receipts make the remembering trustworthy; this module is
what does the remembering.

A Lesson is sealed and chain-linked the same way a tool-call receipt is (mirrors
tool_call_receipt.py exactly): canonical JSON bytes, seal-in-place over a blanked
hex, fixed schema field order, MATCH / TAMPERED / UNVERIFIABLE on re-verify, and
a chain verifier that re-walks prev_hash links. The difference is what the seal
binds: a lesson's seal body carries the derived claim, its source refs (digests,
never payloads), the evidence class, the confidence, the scope boundary, and an
honest-null rationale block.

Design rules (test-enforced):
  - source_refs carry digests, never payloads (organ-bundle spine discipline).
  - rationale is null by default. A null rationale is honest, never fabricated.
  - confidence derives from evidence_class + repetition_count, never asserted:
    single-instance is low, repeated is moderate, cross-operator is high;
    anything uncheckable is unknown. This is the witnessing stamp on the lesson.
  - The chain is re-walkable: verify_lesson_chain returns MATCH / TAMPERED /
    UNVERIFIABLE, mirroring learn's reverify posture.

Standard library only.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA = "flywheel.lesson/v1"

# Lesson kinds -- what class of witnessed event this lesson derives from.
KIND_DRIFT = "drift"
KIND_INTENT_OUTCOME = "intent-outcome"
KIND_MISCONCEPTION = "misconception"
KIND_PATTERN = "pattern"
LESSON_KINDS = frozenset(
    {KIND_DRIFT, KIND_INTENT_OUTCOME, KIND_MISCONCEPTION, KIND_PATTERN}
)

# Source organs -- which flagship produced the witnessed artifact.
SOURCE_ORGANS = frozenset(
    {"learn", "accountable-surface", "mneme", "forum", "flywheel", "crucible", "gather", "index"}
)

# Evidence class -- how many source artifacts converge on this claim.
EVIDENCE_SINGLE = "single-instance"
EVIDENCE_REPEATED = "repeated"
EVIDENCE_CROSS_OPERATOR = "cross-operator"
EVIDENCE_CLASSES = frozenset({EVIDENCE_SINGLE, EVIDENCE_REPEATED, EVIDENCE_CROSS_OPERATOR})

# Confidence -- derived from evidence, never asserted.
CONFIDENCE_HIGH = "high"
CONFIDENCE_MODERATE = "moderate"
CONFIDENCE_LOW = "low"
CONFIDENCE_UNKNOWN = "unknown"
CONFIDENCE_LEVELS = frozenset(
    {CONFIDENCE_HIGH, CONFIDENCE_MODERATE, CONFIDENCE_LOW, CONFIDENCE_UNKNOWN}
)

# Lifecycle status of a lesson in the store.
STATUS_SURFACED = "surfaced"
STATUS_ADMITTED = "admitted"
STATUS_APPLIED = "applied"
STATUS_RETIRED = "retired"
LESSON_STATUSES = frozenset(
    {STATUS_SURFACED, STATUS_ADMITTED, STATUS_APPLIED, STATUS_RETIRED}
)

GENESIS_HASH = "0" * 64

_HE64 = frozenset("0123456789abcdefABCDEF")


# --- canonical bytes + seal (mirrors tool_call_receipt.py) ------------------


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_well_formed(s: str) -> bool:
    return bool(s) and len(s) == 64 and all(c in _HE64 for c in s)


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    """Canonical JSON byte form: compact, UTF-8, ensure_ascii=False, fixed order."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _compute_seal_hash(seal_body: dict[str, Any]) -> str:
    """The sha256 over the canonical seal body bytes."""
    return _sha256_hex(_canonical_bytes(seal_body))


# --- confidence derivation (the witnessing stamp) ---------------------------


def derive_confidence(evidence_class: str, repetition_count: int) -> str:
    """Derive confidence from evidence, never assert it.

    single-instance is low (one artifact could be a fluke).
    repeated is moderate (the same pattern recurred).
    cross-operator is high (independent sources converge).
    Anything uncheckable is unknown. This is the load-bearing rule that keeps a
    lesson honest: confidence is earned by convergence, not declared.
    """
    if evidence_class == EVIDENCE_CROSS_OPERATOR and repetition_count >= 2:
        return CONFIDENCE_HIGH
    if evidence_class == EVIDENCE_REPEATED and repetition_count >= 2:
        return CONFIDENCE_MODERATE
    if evidence_class == EVIDENCE_SINGLE and repetition_count >= 1:
        return CONFIDENCE_LOW
    return CONFIDENCE_UNKNOWN


# --- emission ---------------------------------------------------------------


def build_lesson(
    *,
    kind: str,
    source_organ: str,
    source_refs: list[dict[str, str]],
    claim: str,
    evidence_class: str = EVIDENCE_SINGLE,
    repetition_count: int = 1,
    scope: str = "",
    rationale: dict[str, Any] | None = None,
    seq: int = 0,
    prev_hash: str = GENESIS_HASH,
    status: str = STATUS_SURFACED,
    created_at: str = "",
) -> dict[str, Any]:
    """Build a sealed lesson dict from the witnessed facts.

    ``source_refs`` is a list of ``{organ, ref, digest}`` dicts pointing at the
    witnessed artifacts this lesson derives from. They carry digests, never
    payloads. ``rationale`` is None by default (honest null); when present it
    mirrors the typed rationale block {stated_intent, options_considered,
    chosen_option, confidence}. ``confidence`` is derived from evidence_class +
    repetition_count, never passed in.

    The lesson is built in fixed schema field order so the canonical form is
    stable. The seal_hash and lesson_id are computed last (both content-addressed
    over the seal body).
    """
    if kind not in LESSON_KINDS:
        raise ValueError(f"kind {kind!r} not in {sorted(LESSON_KINDS)}")
    if source_organ not in SOURCE_ORGANS:
        raise ValueError(f"source_organ {source_organ!r} not in {sorted(SOURCE_ORGANS)}")
    if evidence_class not in EVIDENCE_CLASSES:
        raise ValueError(f"evidence_class {evidence_class!r} not in {sorted(EVIDENCE_CLASSES)}")
    if status not in LESSON_STATUSES:
        raise ValueError(f"status {status!r} not in {sorted(LESSON_STATUSES)}")
    if not isinstance(repetition_count, int) or isinstance(repetition_count, bool) or repetition_count < 1:
        raise ValueError("repetition_count must be a positive integer")
    if not isinstance(claim, str) or not claim.strip():
        raise ValueError("claim must be a non-empty string")
    for ref in source_refs:
        if not isinstance(ref, dict) or "digest" not in ref or not _digest_well_formed(ref.get("digest", "")):
            raise ValueError(f"source_ref missing valid 64-char hex digest: {ref!r}")

    confidence = derive_confidence(evidence_class, repetition_count)

    seal_body: dict[str, Any] = {
        "kind": kind,
        "source_organ": source_organ,
        "source_refs": [
            {
                "organ": str(ref.get("organ", source_organ)),
                "ref": str(ref.get("ref", "")),
                "digest": ref["digest"],
            }
            for ref in source_refs
        ],
        "claim": claim,
        "evidence_class": evidence_class,
        "repetition_count": repetition_count,
        "confidence": confidence,
        "scope": scope,
        "rationale": rationale,  # None is honest; JSON null
    }
    seal_hash = _compute_seal_hash(seal_body)
    lesson_id = seal_hash  # content-addressed: the lesson IS its seal body

    return {
        "schema": SCHEMA,
        "lesson_id": lesson_id,
        "seq": seq,
        "prev_hash": prev_hash,
        "seal_hash": seal_hash,
        "seal_body": seal_body,
        "status": status,
        "created_at": created_at,
    }


# --- verification -----------------------------------------------------------

MATCH = "MATCH"
TAMPERED = "TAMPERED"
UNVERIFIABLE = "UNVERIFIABLE"


def verify_lesson(lesson: dict[str, Any]) -> dict[str, Any]:
    """Offline re-verification of one lesson.

    Returns ``{schema, verdict, failure_class, detail}``. The seal is checked
    FIRST (recompute seal_hash over the seal body), before any sealed field is
    interpreted. Then structural and coherence checks run.
    """
    if not isinstance(lesson, dict):
        return _fail("MALFORMED", "lesson is not a JSON object")

    if lesson.get("schema") != SCHEMA:
        return _fail("MALFORMED", f"schema is {lesson.get('schema')!r}, expected {SCHEMA}")

    seal_hash = lesson.get("seal_hash", "")
    if not _digest_well_formed(seal_hash):
        return _fail("DIGEST_MALFORMED", "seal_hash is not a 64-char hex digest")

    seal_body = lesson.get("seal_body")
    if not isinstance(seal_body, dict):
        return _fail("FIELD_CONTRACT_VIOLATION", "seal_body is not an object")

    # Seal check FIRST: recompute over the seal body.
    recomputed = _compute_seal_hash(seal_body)
    if recomputed != seal_hash:
        return _fail(
            "SEAL_MISMATCH",
            f"seal sha256:{seal_hash[:12]}, recomputed sha256:{recomputed[:12]}",
        )

    # lesson_id must equal the seal_hash (content-addressed identity).
    if lesson.get("lesson_id") != seal_hash:
        return _fail(
            "FIELD_CONTRACT_VIOLATION",
            "lesson_id does not match seal_hash (content-addressed identity broken)",
        )

    # Structural checks on the seal body fields.
    kind = seal_body.get("kind", "")
    if kind not in LESSON_KINDS:
        return _fail("FIELD_CONTRACT_VIOLATION", f"seal_body.kind {kind!r} not a valid lesson kind")

    source_organ = seal_body.get("source_organ", "")
    if source_organ not in SOURCE_ORGANS:
        return _fail("FIELD_CONTRACT_VIOLATION", f"seal_body.source_organ {source_organ!r} not a valid organ")

    evidence_class = seal_body.get("evidence_class", "")
    if evidence_class not in EVIDENCE_CLASSES:
        return _fail("FIELD_CONTRACT_VIOLATION", f"seal_body.evidence_class {evidence_class!r} not valid")

    confidence = seal_body.get("confidence", "")
    if confidence not in CONFIDENCE_LEVELS:
        return _fail("FIELD_CONTRACT_VIOLATION", f"seal_body.confidence {confidence!r} not valid")

    # Confidence must be honestly derived (not asserted higher than evidence warrants).
    repetition_count = seal_body.get("repetition_count", 0)
    if not isinstance(repetition_count, int) or isinstance(repetition_count, bool) or repetition_count < 1:
        return _fail("FIELD_CONTRACT_VIOLATION", "repetition_count must be a positive integer")
    expected_confidence = derive_confidence(evidence_class, repetition_count)
    if confidence != expected_confidence:
        return _fail(
            "FIELD_CONTRACT_VIOLATION",
            f"confidence {confidence!r} inflated: evidence ({evidence_class}, {repetition_count}) "
            f"warrants {expected_confidence!r}",
        )

    # source_refs must each carry a valid digest.
    source_refs = seal_body.get("source_refs", [])
    if not isinstance(source_refs, list) or len(source_refs) == 0:
        return _fail("FIELD_CONTRACT_VIOLATION", "seal_body.source_refs must be a non-empty list")
    for i, ref in enumerate(source_refs):
        if not isinstance(ref, dict) or not _digest_well_formed(ref.get("digest", "")):
            return _fail("DIGEST_MALFORMED", f"source_refs[{i}].digest is not a 64-char hex digest")

    # rationale must be None or a dict (never a fabricated string).
    rationale = seal_body.get("rationale")
    if rationale is not None and not isinstance(rationale, dict):
        return _fail("FIELD_CONTRACT_VIOLATION", "seal_body.rationale must be null or an object")

    status = lesson.get("status", "")
    if status not in LESSON_STATUSES:
        return _fail("FIELD_CONTRACT_VIOLATION", f"status {status!r} not a valid lesson status")

    prev_hash = lesson.get("prev_hash", "")
    if prev_hash != GENESIS_HASH and not _digest_well_formed(prev_hash):
        return _fail("DIGEST_MALFORMED", "prev_hash is not the genesis or a 64-char hex digest")

    return {
        "schema": SCHEMA,
        "verdict": MATCH,
        "lesson_id": seal_hash,
        "status": status,
        "confidence": confidence,
    }


def _fail(failure_class: str, detail: str) -> dict[str, Any]:
    verdict = TAMPERED if failure_class == "SEAL_MISMATCH" else UNVERIFIABLE
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "failure_class": failure_class,
        "detail": detail,
    }


def verify_lesson_chain(lessons: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify a chain of lessons: each seal + chain linkage.

    Each lesson's prev_hash must equal the seal_hash of the prior lesson (or the
    genesis hash for the first). Returns a summary with per-lesson verdicts and
    an overall verdict (MATCH only if every lesson verifies AND the chain links
    hold).
    """
    if not lessons:
        return {"verdict": UNVERIFIABLE, "detail": "empty chain", "lessons": []}

    results: list[dict[str, Any]] = []
    chain_ok = True
    expected_prev = GENESIS_HASH
    for i, lesson in enumerate(lessons):
        v = verify_lesson(lesson)
        if v.get("verdict") != MATCH:
            chain_ok = False
            results.append(v)
            continue
        # chain linkage
        actual_prev = lesson.get("prev_hash", "")
        if actual_prev != expected_prev:
            chain_ok = False
            results.append(
                {
                    **v,
                    "verdict": TAMPERED,
                    "failure_class": "CHAIN_BROKEN",
                    "detail": f"prev_hash mismatch at seq {i}",
                }
            )
        else:
            results.append(v)
        # next expected prev is this lesson's seal_hash
        expected_prev = lesson.get("seal_hash", "")

    return {
        "verdict": MATCH if chain_ok else TAMPERED,
        "n": len(lessons),
        "lessons": results,
    }
