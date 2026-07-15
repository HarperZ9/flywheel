"""retention.py -- durable learning gets its own receipt.

The dossier's learning findings separate performance-at-acceptance from
retained competence: Copilot-paired novices won the day and lost the week
(arXiv 2604.18538). So the platform re-surfaces checked evidence after a
delay: `retention_due` lists comprehension and attestation entities old
enough for a retest that have none recorded; `retention_record` GRADES an
unaided answer against the original receipt's key material and banks the
graded outcome linked to the original, so the ledger distinguishes what
someone once demonstrated from what they still hold.

Two gates keep the retest honest. The interval: a retest younger than the
schedule is refused (spacing IS the mechanism; an immediate replay measures
nothing) unless a waiver is DECLARED in the receipt, never silent. The
grade: the caller supplies an answer, not a verdict; coverage of the
original's key_terms and files decides passed, re-runnable by a stranger.
The retest itself remains a surface action and unaided BY DESIGN -- the
platform schedules honesty, it does not sit the exam for you.
"""
from __future__ import annotations

import hashlib
import time

SCHEMA = "flywheel.retention/v1"
RECEIPT_SCHEMA = "flywheel.retention-receipt/v2"


def retention_due(days: float = 3.0,
                  kinds: tuple = ("comprehension", "attestation")) -> dict:
    """Checked evidence older than `days` with no retention receipt yet."""
    from .store import query_all_entities, relations_of
    cutoff = time.time() - days * 86400.0
    due = []
    scanned = 0
    for kind in kinds:
        for meta in query_all_entities(kind=kind):
            scanned += 1
            if meta["created"] > cutoff:
                continue
            if any(r["kind"] == "retention"
                   for r in relations_of(meta["eid"])):
                continue
            due.append({"eid": meta["eid"], "kind": kind,
                        "age_days": round(
                            (time.time() - meta["created"]) / 86400.0, 2)})
    return {"schema": SCHEMA, "days": days, "due": due,
            "scanned": scanned, "complete": True,
            "note": "the retest is a surface action and unaided by design; "
                    "the platform schedules honesty, it does not sit the "
                    "exam; scanned is the full paged count, not a silent "
                    "newest-page truncation"}


def retention_record(original_eid: str, answer: str, *, note: str = "",
                     min_days: float = 3.0, threshold: float = 0.6,
                     waive_interval_reason: str = "") -> dict:
    """Grade an unaided retest answer against the original's key material and
    bank the graded outcome, linked to the original evidence. The caller
    supplies the ANSWER; the grade is derived, never self-declared."""
    from .store import get_entity, put_entity, put_relation
    if not isinstance(answer, str) or not answer.strip():
        return {"error": "the retest is graded: provide 'answer' text, not a "
                         "self-declared outcome"}
    original = get_entity(original_eid)
    if original is None:
        return {"error": f"no such entity: {original_eid}"}
    data = original.get("data") or {}
    terms = [str(t) for t in (data.get("key_terms") or []) if str(t).strip()]
    files = [str(f) for f in (data.get("files") or []) if str(f).strip()]
    if not terms:
        return {"error": "original carries no key material (key_terms) to "
                         "grade an unaided retest against"}
    age_days = (time.time() - float(original.get("created") or 0.0)) / 86400.0
    if age_days < min_days and not waive_interval_reason:
        return {"error": f"retest too soon: the original is "
                         f"{age_days:.2f} days old and the schedule is "
                         f"{min_days} days; spacing is the mechanism, an "
                         "immediate replay measures nothing"}
    text = answer.lower()
    mentioned = [t for t in terms if t.lower() in text]
    missed = [t for t in terms if t.lower() not in text]
    mentioned_files = [f for f in files if f.lower() in text]
    coverage = round(len(mentioned) / len(terms), 4)
    passed = coverage >= threshold and (not files or bool(mentioned_files))
    doc = {"schema": RECEIPT_SCHEMA, "original": original_eid,
           "original_sha256": original["sha256"],
           "passed": passed, "coverage": coverage, "threshold": threshold,
           "mentioned": mentioned, "missed": missed,
           "files": files, "mentioned_files": mentioned_files,
           "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
           "waived_interval": waive_interval_reason or None,
           "note": note}
    stored = put_entity("retention", doc)
    put_relation(original_eid, stored.get("eid", ""), "retention")
    return {**doc, "stored": stored.get("eid", ""),
            "chain_hash": stored.get("chain_hash", "")}
