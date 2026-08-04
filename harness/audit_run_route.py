"""audit_run_route.py -- the audit surface behind the gateway's thin stubs.

Two handlers, both returning (body, http_code) in the gateway's own vocabulary:

  handle_audit_run    -- review a completed unit of work (its sealed work
                         receipt plus an optional artifact) with a small
                         deterministic detector set, roll the findings into a
                         bounded verdict, optionally add a cheap model narrative,
                         and seal it all into an audit receipt CHAINED onto the
                         work receipt.
  handle_audit_verify -- re-check an audit receipt (and, when a work receipt is
                         supplied, its chain link) with the offline verifier.

The reviewer is cheap by construction: it runs deterministically with NO model,
and adds a model narrative only when an ``endpoint`` is supplied AND buildable AND
answers. Offline degrades the summary to an honest-null reason -- never a 502 for
a missing narrator. make_endpoint_proposer is kept as a module-level name so a
test can substitute it and exercise the whole route with no real model.

The deterministic detectors are a STARTER set (clearly labelled, extensible),
mirroring the finding shape of the sibling agent-audit project so the two
interoperate. agent-audit's fuller detector library is the reference this can
later adopt; it is NOT a runtime dependency (flywheel's gate job runs on a bare
interpreter), so these are re-implemented in stdlib here.

Python 3.10-safe (datetime.timezone.utc, never the 3.11 datetime.UTC alias).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit_receipt import build_audit_receipt, emit_audit_receipt, verify_audit_receipt
from .endpoint_registry import make_endpoint_proposer
from .tool_call_receipt import _canonical_bytes, _digest_well_formed, _sha256_hex

# The starter detector set. A universal, domain-agnostic slice: it always runs,
# and domain oracles can be layered later without replacing it.
_STARTER_DETECTORS = ("receipt_integrity", "honest_null_presence", "unbacked_claim")

# Mirrors agent-audit's _CLAIMED_HISTORY_MARKERS verbatim (agent-audit.report.v1),
# so an "unbacked prior-work claim" flagged here means what it means there.
_CLAIMED_HISTORY_MARKERS = (
    "i previously", "i already", "i have completed",
    "after completing", "given my earlier", "having run",
)
# Cheap signals that a record REPORTS an outcome (so an honest-null is expected).
_RESULT_MARKERS = ("results", "verdict", "outcome", "accepted", "passed")
# Honest-null markers that satisfy that expectation.
_HONEST_NULL_MARKERS = ("does_not_prove", "honest_null", "unverifiable",
                        "no uplift", "not proven", "unknown")

_SYS = ("You are a terse reviewer of completed work. Given deterministic findings "
        "about one unit of work, write two or three plain sentences naming what a "
        "developer should look at first. Do not invent findings; summarize only "
        "the ones given. No preamble, no restating the task.")


def _now_iso() -> str:
    """UTC timestamp, timezone-aware. datetime.timezone.utc (never the 3.11
    datetime.UTC alias) so the module runs on Python 3.10."""
    return datetime.now(timezone.utc).isoformat()


def _review(detector_id: str, dimension: str, severity: str, summary: str) -> dict[str, str]:
    return {"detector_id": detector_id, "dimension": dimension,
            "severity": severity, "summary": summary}


def _detect_integrity(work_receipt: dict) -> tuple[str, dict[str, str]]:
    """Does the work receipt's own seal re-derive? Returns (status, review) where
    status is intact / mismatch / unverifiable. A mismatch is a re-derivation, not
    an opinion, so it earns a CRITICAL finding and the audit's high confidence."""
    seal = work_receipt.get("seal") if isinstance(work_receipt, dict) else None
    hexv = str(seal.get("hex", "")) if isinstance(seal, dict) else ""
    if not _digest_well_formed(hexv):
        return "unverifiable", _review(
            "receipt_integrity", "correctness", "WARN",
            "the work receipt carries no well-formed seal, so its integrity could "
            "not be re-derived here")
    probe = dict(work_receipt)
    probe["seal"] = {"algorithm": "sha256", "hex": ""}
    recomputed = _sha256_hex(_canonical_bytes(probe))
    if recomputed == hexv:
        return "intact", _review(
            "receipt_integrity", "correctness", "INFO",
            f"the work receipt seal re-derives (sha256:{hexv[:12]}); the record is intact")
    return "mismatch", _review(
        "receipt_integrity", "correctness", "CRITICAL",
        f"the work receipt seal does NOT re-derive (stored sha256:{hexv[:12]}, "
        f"recomputed sha256:{recomputed[:12]}); the record was altered after sealing")


def _detect_honest_null(artifact: str) -> dict[str, str] | None:
    """Scan the WORK-PRODUCT prose (the artifact), not the receipt's structural
    fields: a Layer-1 receipt legitimately carries no quality honest-null (that
    is this audit's job), so keying off the receipt would flag every work. When
    the artifact reports a result but states no limit, that is the shape that
    overclaims -- WARN. With no artifact prose, this dimension is left unjudged."""
    low = artifact.lower()
    reports = any(m in low for m in _RESULT_MARKERS)
    has_null = any(m in low for m in _HONEST_NULL_MARKERS)
    if reports and not has_null:
        return _review(
            "honest_null_presence", "completeness", "WARN",
            "the work product reports a result but states no honest-null / limit; "
            "a result with no stated bound is the shape that overclaims")
    return None


def _detect_unbacked_claims(artifact: str) -> dict[str, str] | None:
    """Mirror agent-audit's claimed-history detector over the artifact text: a
    claim of prior work that no receipt in the chain backs is a flag to check."""
    low = artifact.lower()
    marker = next((m for m in _CLAIMED_HISTORY_MARKERS if m in low), "")
    if not marker:
        return None
    return _review(
        "unbacked_claim", "consistency", "WARN",
        f"the work text claims prior work ({marker!r}) that no receipt in this chain "
        f"backs; confirm it against the record before relying on it")


def _rollup(reviews: list[dict[str, str]]) -> str:
    """Any CRITICAL -> FAIL; any WARN -> CONCERNS; else PASS. A bounded verdict,
    never an optimality claim."""
    sev = {r["severity"] for r in reviews}
    if "CRITICAL" in sev:
        return "FAIL"
    if "WARN" in sev:
        return "CONCERNS"
    return "PASS"


def _confidence(integrity_status: str) -> str:
    """A label, not a number. A re-derived tamper is high (it is arithmetic); an
    unverifiable seal is low (we could not even anchor); otherwise moderate (a
    cheap reviewer's opinion)."""
    if integrity_status == "mismatch":
        return "high"
    if integrity_status == "unverifiable":
        return "low"
    return "moderate"


def _det_summary(reviews: list[dict[str, str]], verdict: str) -> str:
    lines = [f"{r['severity']} {r['dimension']}: {r['summary']}" for r in reviews]
    return f"verdict {verdict} over {len(reviews)} review(s). " + " | ".join(lines)


def _narrate(reviews, verdict, endpoint, model) -> tuple[str, bool, str, str]:
    """(summary, narrated, model_ref, note). The deterministic base always holds;
    a model narrative replaces it only when an endpoint is supplied AND buildable
    AND answers. Any absence or failure degrades to the base with an honest note,
    never an error -- the missing narrator is a null, not a 502."""
    base = _det_summary(reviews, verdict)
    if not endpoint:
        return base, False, "", "no reviewer endpoint was supplied; the summary is deterministic"
    try:
        prop = make_endpoint_proposer(endpoint, model=model or None)
        prompt = base + "\n\nWrite the developer-facing summary now."
        out = prop.generate(prompt, seed=0, temperature=0.0, max_new_tokens=256, system=_SYS)
        text = (getattr(out, "text", "") or "").strip()
        if text:
            return text, True, (getattr(prop, "model_ref", "") or model or endpoint), ""
        return base, False, "", "the reviewer model returned nothing; the summary is deterministic"
    except Exception as e:  # noqa: BLE001 -- a missing narrator degrades, never 502s
        return base, False, "", (f"the reviewer model was unreachable "
                                 f"({type(e).__name__}); the summary is deterministic")


def _does_not_prove(integrity_status: str, narrated: bool, note: str) -> str:
    """The honest null, always non-empty. Names what this audit could not judge."""
    parts = ["this is a cheap post-work review, an opinion with a confidence and not "
             "a proof; a PASS means only that this starter detector set found nothing, "
             "not that the work is correct"]
    if integrity_status == "unverifiable":
        parts.append("the work receipt seal could not be re-derived, so even the "
                     "integrity of the reviewed record is unproven here")
    if not narrated:
        parts.append(note or "no model narrative was produced; the summary is "
                             "deterministic only")
    return "; ".join(parts) + "."


def _subject_digest(work_receipt: dict, artifact: str) -> str:
    """The canonical hash of the reviewed work (work receipt + artifact). The
    audit binds to this digest, never to the work body."""
    payload = json.dumps({"work_receipt": work_receipt, "artifact": artifact},
                         sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return _sha256_hex(payload)


def handle_audit_run(req: dict, run_root) -> tuple[dict, int]:
    """Review a work receipt and return the sealed, chained audit receipt.

    req: {"work_receipt": <a sealed receipt dict, required>, "artifact":
    <optional str>, "endpoint": <optional>, "model": <optional>}. A missing or
    non-dict work_receipt is a 400. The audit always succeeds otherwise: offline
    it is deterministic, and an unreachable narrator degrades to an honest null.
    """
    work_receipt = req.get("work_receipt")
    if not isinstance(work_receipt, dict):
        return {"error": "provide a 'work_receipt' object (a sealed receipt dict)"}, 400
    artifact = req.get("artifact")
    artifact = artifact if isinstance(artifact, str) else ""
    endpoint = str(req.get("endpoint") or "").strip()
    model = req.get("model")
    model = str(model).strip() if isinstance(model, str) and model.strip() else None

    started = _now_iso()
    integrity_status, integrity_review = _detect_integrity(work_receipt)
    reviews = [integrity_review]
    hn = _detect_honest_null(artifact)
    if hn is not None:
        reviews.append(hn)
    claim = _detect_unbacked_claims(artifact)
    if claim is not None:
        reviews.append(claim)

    verdict = _rollup(reviews)
    confidence = _confidence(integrity_status)
    summary, narrated, model_ref, note = _narrate(reviews, verdict, endpoint, model)
    reviewer = f"flywheel-audit/starter+{model_ref}" if narrated else "flywheel-audit/starter"
    dnp = _does_not_prove(integrity_status, narrated, note)
    finished = _now_iso()

    work_hex = ""
    if isinstance(work_receipt.get("seal"), dict):
        work_hex = str(work_receipt["seal"].get("hex", ""))
    run_id = f"audit-{os.urandom(4).hex()}"
    receipt = build_audit_receipt(
        run_id=run_id, work_receipt_sha256=work_hex,
        subject_digest=_subject_digest(work_receipt, artifact),
        reviewer=reviewer, reviews=reviews, summary=summary,
        verdict=verdict, confidence=confidence, does_not_prove=dnp,
        started_utc=started, finished_utc=finished)

    written = emit_audit_receipt(receipt, Path(run_root) / "audit")
    # receipt_file is a BARE filename, never an absolute path -- a receipt is
    # portable, and its on-disk location is the running host's business.
    receipt_file = written.name if written is not None else ""
    return {"schema": "flywheel.audit-run/v1", "verdict": verdict,
            "confidence": confidence, "reviewer": reviewer, "narrated": narrated,
            "reviews": reviews, "summary": summary, "does_not_prove": dnp,
            "detectors": list(_STARTER_DETECTORS), "work_receipt_sha256": work_hex,
            "receipt": receipt, "receipt_file": receipt_file}, 200


def handle_audit_verify(req: dict) -> tuple[dict, int]:
    """Re-check an audit receipt offline. Always 200: the verdict itself carries
    the news (MATCH / TAMPERED / UNVERIFIABLE), so a corrupted receipt or a broken
    chain is a first-class result, not an HTTP error. When ``work_receipt`` is
    supplied, the chain link back to the work is confirmed too."""
    audit_receipt = req.get("audit_receipt")
    work_receipt = req.get("work_receipt")
    ar = audit_receipt if isinstance(audit_receipt, dict) else None
    wr = work_receipt if isinstance(work_receipt, dict) else None
    return verify_audit_receipt(ar, work_receipt=wr), 200
