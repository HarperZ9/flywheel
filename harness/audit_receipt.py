"""audit_receipt.py -- the sealed, chain-linked, domain-agnostic AUDIT receipt.

Layer 2 to the work receipt's Layer 1. The work receipt (tool-call / eval) says
a record is intact and its own; it makes no quality claim. This audit receipt
renders a SEPARATE developer-facing judgment -- reviews across domain-neutral
dimensions, a bounded verdict, a confidence label, and an honest-null
does_not_prove -- and CHAINS that judgment onto the work receipt it reviewed.
The two never merge: a green work receipt on weak work stays green, and this is
where "weak work" gets named, as an opinion with a confidence, never a proof.

Chaining: prev_receipt_sha256 = the work receipt's seal hex (equivalently its
blanked-seal canonical recompute). verify_audit_receipt(receipt, work_receipt)
confirms that exact link, so a stranger proves the audit reviewed THAT work and
neither was altered after.

The reviewed work is stored ONLY as a subject digest and review counts, never
the work body -- the same no-floats, no-absolute-paths, string-typed discipline
as every other receipt here, so the audit receipt is itself byte-for-byte
re-derivable and offline-verifiable.

This reuses tool_call_receipt.py's seal verbatim and adds NO third-party import,
so verify_audit_receipt runs on a bare interpreter (the verifier-stdlib gate
covers it). It mirrors the finding shape of the sibling agent-audit project
(AuditFinding{detector_id, severity, summary}, schema agent-audit.report.v1) so
the two interoperate; agent-audit's fuller detector library is the reference this
layer can later adopt.

Standard library only, and free of any version-gated feature, so the verifier
path stays portable below the package floor for a stranger to re-run. (The
verifier-closure floor gate in tests/test_python_floor.py enforces exactly that,
which is why this note carries no version-gated token to trip its scanner.)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .tool_call_receipt import (
    MATCH,
    TAMPERED,
    UNVERIFIABLE,
    _canonical_bytes,
    _digest_well_formed,
    _seal_receipt,
    _sha256_hex,
)

SCHEMA = "flywheel.audit-receipt/v1"

# The per-review fields, in fixed order. A review is one detector's disposition
# over one domain-neutral dimension. No floats, no free-form extra keys.
_REVIEW_FIELDS = ("detector_id", "dimension", "severity", "summary")

# The bounded verdict roll-up. Never an optimality claim -- a FAIL is a flag to
# investigate, not a verdict of fact.
VERDICTS = frozenset({"PASS", "CONCERNS", "FAIL"})
# Confidence is a label, never a number: cheap local review is weaker than a
# hosted one, and the reader weights it by this word (and the reviewer field).
CONFIDENCE_LABELS = frozenset({"high", "moderate", "low", "unknown"})
# The domain-agnostic dimensions. A rubric, not a per-domain ruleset.
DIMENSIONS = frozenset(
    {"correctness", "completeness", "consistency", "risk", "clarity"}
)
# Finding severities, matching agent-audit's AlertSeverity vocabulary.
SEVERITIES = frozenset({"INFO", "WARN", "CRITICAL"})


def _normalize_reviews(reviews: Any) -> list[dict[str, str]]:
    """Each review down to exactly the fixed fields, all strings. Unknown fields
    dropped (additionalProperties: false)."""
    out: list[dict[str, str]] = []
    for r in reviews or []:
        r = r if isinstance(r, dict) else {}
        out.append({
            "detector_id": str(r.get("detector_id", "")),
            "dimension": str(r.get("dimension", "")),
            "severity": str(r.get("severity", "")),
            "summary": str(r.get("summary", "")),
        })
    return out


def build_audit_receipt(
    *,
    run_id: str,
    work_receipt_sha256: str,
    subject_digest: str,
    reviewer: str,
    reviews: Any,
    summary: str,
    verdict: str,
    confidence: str,
    does_not_prove: str,
    started_utc: str,
    finished_utc: str,
) -> dict[str, Any]:
    """Build a sealed audit receipt in the fixed schema field order.

    The reviewed work is stored ONLY as ``subject.sha256`` (a canonical hash of
    the work receipt plus any artifact) and ``subject.n_reviews`` -- never the
    work body. ``work_receipt_sha256`` becomes ``prev_receipt_sha256``, the chain
    link back to the work. The seal is the shared blanked-seal canonical-bytes
    hash, so a stranger re-checks it with the discipline every other receipt uses.
    """
    norm = _normalize_reviews(reviews)
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "run_id": str(run_id),
        "reviewer": str(reviewer),
        "subject": {"sha256": str(subject_digest), "n_reviews": str(len(norm))},
        "reviews": norm,
        "summary": str(summary),
        "verdict": str(verdict),
        "confidence": str(confidence),
        "does_not_prove": str(does_not_prove),
        "started_utc": str(started_utc),
        "finished_utc": str(finished_utc),
        "prev_receipt_sha256": str(work_receipt_sha256 or ""),
        "seal": {"algorithm": "sha256", "hex": ""},
    }
    _seal_receipt(receipt)
    return receipt


def _fail(failure_class: str, detail: str) -> dict[str, Any]:
    """A tampered sealed body is TAMPERED; a broken chain is TAMPERED (the audit
    no longer binds the work it claims); anything else is UNVERIFIABLE. Same
    taxonomy split as every other receipt family, one vocabulary for a caller."""
    verdict = (TAMPERED if failure_class in ("SEAL_MISMATCH", "CHAIN_BROKEN")
               else UNVERIFIABLE)
    return {"schema": SCHEMA, "verdict": verdict,
            "failure_class": failure_class, "detail": detail}


def verify_audit_receipt(receipt: dict[str, Any],
                         work_receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    """Offline re-verification. Returns {verdict, failure_class, detail}.

    The checks run in the only safe order: SCHEMA first, then the SEAL (so no
    sealed field is interpreted until the seal is proven), then digest
    well-formedness, then the field contracts. When a ``work_receipt`` is
    supplied, the chain link is confirmed LAST: ``prev_receipt_sha256`` must
    equal the work receipt's seal hex, else CHAIN_BROKEN. Import-clean stdlib.
    """
    if not isinstance(receipt, dict):
        return _fail("MALFORMED", "receipt is not a JSON object")
    if receipt.get("schema") != SCHEMA:
        return _fail("MALFORMED",
                     f"schema is {receipt.get('schema')!r}, expected {SCHEMA}")

    # --- seal first -----------------------------------------------------------
    seal = receipt.get("seal")
    if not isinstance(seal, dict) or seal.get("algorithm") != "sha256":
        return _fail("MALFORMED", "seal missing or algorithm is not sha256")
    stored_hex = seal.get("hex", "")
    if not _digest_well_formed(stored_hex):
        return _fail("DIGEST_MALFORMED", "seal.hex is not a 64-char hex digest")
    probe = dict(receipt)
    probe["seal"] = {"algorithm": "sha256", "hex": ""}
    recomputed = _sha256_hex(_canonical_bytes(probe))
    if recomputed != stored_hex:
        return _fail("SEAL_MISMATCH",
                     f"seal sha256:{stored_hex[:12]}, "
                     f"recomputed sha256:{recomputed[:12]}")

    # --- digest well-formedness ----------------------------------------------
    subject = receipt.get("subject")
    if not isinstance(subject, dict):
        return _fail("FIELD_CONTRACT_VIOLATION", "subject is not an object")
    if not _digest_well_formed(subject.get("sha256", "")):
        return _fail("DIGEST_MALFORMED",
                     "subject.sha256 is not a 64-char hex digest")
    prev = receipt.get("prev_receipt_sha256", "")
    if prev and not _digest_well_formed(prev):
        return _fail("DIGEST_MALFORMED",
                     "prev_receipt_sha256 is not a 64-char hex digest")

    # --- field contracts ------------------------------------------------------
    reviews = receipt.get("reviews")
    if not isinstance(reviews, list):
        return _fail("FIELD_CONTRACT_VIOLATION", "reviews is not a list")
    n_reviews = subject.get("n_reviews", "")
    if not (isinstance(n_reviews, str) and n_reviews.isdigit()
            and int(n_reviews) == len(reviews)):
        return _fail("FIELD_CONTRACT_VIOLATION",
                     "subject.n_reviews is not a digit string equal to len(reviews)")
    for i, r in enumerate(reviews):
        if not isinstance(r, dict) or set(r.keys()) != set(_REVIEW_FIELDS):
            return _fail("FIELD_CONTRACT_VIOLATION",
                         f"review {i} fields != {_REVIEW_FIELDS}")
        if r.get("severity") not in SEVERITIES:
            return _fail("FIELD_CONTRACT_VIOLATION",
                         f"review {i} severity {r.get('severity')!r} is not a "
                         f"known severity")
        if r.get("dimension") not in DIMENSIONS:
            return _fail("FIELD_CONTRACT_VIOLATION",
                         f"review {i} dimension {r.get('dimension')!r} is not a "
                         f"known dimension")
    if receipt.get("verdict") not in VERDICTS:
        return _fail("FIELD_CONTRACT_VIOLATION",
                     f"verdict {receipt.get('verdict')!r} is not PASS/CONCERNS/FAIL")
    if receipt.get("confidence") not in CONFIDENCE_LABELS:
        return _fail("FIELD_CONTRACT_VIOLATION",
                     f"confidence {receipt.get('confidence')!r} is not a known label")
    if not str(receipt.get("does_not_prove", "")).strip():
        return _fail("FIELD_CONTRACT_VIOLATION",
                     "does_not_prove is empty; an audit must keep its honest null")

    # --- chain link (only when the work receipt is supplied) ------------------
    if work_receipt is not None:
        work_hex = ""
        if isinstance(work_receipt, dict) and isinstance(work_receipt.get("seal"), dict):
            work_hex = str(work_receipt["seal"].get("hex", ""))
        if prev != work_hex:
            return _fail("CHAIN_BROKEN",
                         f"prev_receipt_sha256 sha256:{(prev or '(none)')[:12]} "
                         f"!= work receipt seal sha256:{(work_hex or '(none)')[:12]}")

    return {
        "schema": SCHEMA,
        "verdict": MATCH,
        "failure_class": "",
        "detail": f"{len(reviews)} review(s), verdict {receipt.get('verdict')} "
                  f"(confidence {receipt.get('confidence')}); "
                  f"chained to sha256:{prev[:12] if prev else '(none)'}",
        "run_id": receipt.get("run_id", ""),
        "audit_verdict": receipt.get("verdict", ""),
        "confidence": receipt.get("confidence", ""),
        "prev_receipt_sha256": prev,
        "seal": {"algorithm": "sha256", "hex": stored_hex},
    }


def emit_audit_receipt(receipt: dict[str, Any], receipt_dir: Path) -> Path | None:
    """Write one sealed audit receipt to ``receipt_dir``. Never raises.

    Mirrors emit_eval_receipt: mkdir parents, write compact JSON, swallow any
    failure to stderr, return the Path written or None. The filename carries the
    run_id and a short seal prefix, and is BARE (never an absolute path).
    """
    try:
        receipt_dir.mkdir(parents=True, exist_ok=True)
        run_id = str(receipt.get("run_id", "run"))
        safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in run_id)[:48]
        seal_hex = str(receipt.get("seal", {}).get("hex", ""))[:12] or "unsealed"
        filename = f"audit-receipt-{safe}-{seal_hex}.json"
        path = receipt_dir / filename
        path.write_text(
            json.dumps(receipt, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path
    except Exception as exc:  # noqa: BLE001 -- emission must never break the run path
        print(f"audit-receipt: emission failed (non-fatal): {exc}", file=sys.stderr)
        return None
