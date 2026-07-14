"""comprehension_ledger.py -- ownership from checked evidence, not git blame.

The substrate collapse (arXiv 2606.20882): authorship metrics assumed that
writing code is evidence of understanding it, and models broke that
assumption. This ledger is the replacement the paper calls for: per file,
who most recently DEMONSTRATED engagement through a checked artifact -- a
COMPLETE attestation (they walked every edited file) or a PASSED
comprehension receipt (their explanation engaged with the actual change).
Partial walks and failed gates confer nothing; recency wins; every row
points at the store entity a stranger can fetch and re-check.
"""
from __future__ import annotations

SCHEMA = "flywheel.comprehension-ledger/v1"


def _rows(kind: str, project: "str | None"):
    from .store import get_entity, query_entities
    for meta in query_entities(kind=kind, project=project):
        entity = get_entity(meta["eid"])
        if entity and isinstance(entity.get("data"), dict):
            yield entity


def comprehension_ledger(*, project: "str | None" = None) -> dict:
    """Project the store's checked evidence into per-file holdership.
    Candidate claims from BOTH kinds are merged and sorted newest-first
    by the entity's created time, so recency wins ACROSS kinds: an older
    attestation never blocks a newer passed comprehension on the same
    file, and vice versa."""
    files: dict = {}

    def claim(path: str, holder: str, kind: str, eid: str, created: float):
        if path and path not in files:
            files[path] = {"holder": holder, "kind": kind,
                           "eid": eid, "at": created}

    candidates = []   # (created, kind, holder, path, eid)
    for e in _rows("attestation", project):
        d = e["data"]
        if d.get("standing") == "complete":
            for path in d.get("reviewed") or []:
                candidates.append((e["created"], "attestation",
                                   str(d.get("reviewer", "")), str(path),
                                   e["eid"]))
    for e in _rows("comprehension", project):
        d = e["data"]
        if d.get("passed") is True:
            for path in d.get("files") or []:
                candidates.append((e["created"], "comprehension",
                                   str(d.get("reviewer", "")), str(path),
                                   e["eid"]))
    # newest first; first-write-wins per path then holds the latest claim
    candidates.sort(key=lambda c: c[0], reverse=True)
    for created, kind, holder, path, eid in candidates:
        claim(path, holder, kind, eid, created)

    holders: dict = {}
    for row in files.values():
        holders[row["holder"]] = holders.get(row["holder"], 0) + 1
    note = ("holdership = the latest COMPLETE attestation or PASSED "
            "comprehension receipt per file; partial or failed evidence "
            "confers nothing")
    if not files:
        note = "no checked evidence yet; " + note
    return {"schema": SCHEMA, "files": files, "holders": holders,
            "note": note}
