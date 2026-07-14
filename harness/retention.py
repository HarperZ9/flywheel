"""retention.py -- durable learning gets its own receipt.

The dossier's learning findings separate performance-at-acceptance from
retained competence: Copilot-paired novices won the day and lost the week
(arXiv 2604.18538). So the platform re-surfaces checked evidence after a
delay: `retention_due` lists comprehension and attestation entities old
enough for a retest that have none recorded; `retention_record` banks the
unaided outcome as a store entity linked to the original, so the ledger
distinguishes what someone once demonstrated from what they still hold.
The retest itself is a surface action and unaided BY DESIGN -- the
platform schedules honesty, it does not sit the exam for you.
"""
from __future__ import annotations

import time

SCHEMA = "flywheel.retention/v1"
RECEIPT_SCHEMA = "flywheel.retention-receipt/v1"


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


def retention_record(original_eid: str, passed: bool, *,
                     note: str = "") -> dict:
    """Bank an unaided retest outcome, linked to the original evidence."""
    from .store import get_entity, put_entity, put_relation
    original = get_entity(original_eid)
    if original is None:
        return {"error": f"no such entity: {original_eid}"}
    doc = {"schema": RECEIPT_SCHEMA, "original": original_eid,
           "original_sha256": original["sha256"],
           "passed": bool(passed), "note": note}
    stored = put_entity("retention", doc)
    put_relation(original_eid, stored.get("eid", ""), "retention")
    return {**doc, "stored": stored.get("eid", ""),
            "chain_hash": stored.get("chain_hash", "")}
