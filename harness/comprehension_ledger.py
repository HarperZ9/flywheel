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
    from .store import get_entity, query_all_entities
    for meta in query_all_entities(kind=kind, project=project):
        entity = get_entity(meta["eid"])
        if entity and isinstance(entity.get("data"), dict):
            yield entity


def _norm_path(path: str) -> str:
    """One spelling per file: posix separators, no leading ./ — so an
    attestation's repo path and a comprehension receipt's diff path meet
    on the same ledger key."""
    p = str(path).replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def _failed_latest_retest(eid: str) -> "str | None":
    """The eid of the NEWEST retention receipt linked to this evidence if
    that retest FAILED, else None. A failed unaided retest revokes the
    row: once demonstrated is not still held."""
    from .store import get_entity, relations_of
    newest, newest_created = None, -1.0
    for rel in relations_of(eid):
        if rel.get("kind") != "retention" or rel.get("src") != eid:
            continue
        r = get_entity(rel.get("dst", ""))
        if r and r.get("created", 0) > newest_created:
            newest, newest_created = r, r["created"]
    if newest and (newest.get("data") or {}).get("passed") is False:
        return newest["eid"]
    return None


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
                                   str(d.get("reviewer", "")),
                                   _norm_path(path), e["eid"]))
    for e in _rows("comprehension", project):
        d = e["data"]
        if d.get("passed") is True:
            for path in d.get("files") or []:
                candidates.append((e["created"], "comprehension",
                                   str(d.get("reviewer", "")),
                                   _norm_path(path), e["eid"]))
    # newest first; first-write-wins per path then holds the latest claim.
    # An entity whose newest linked retest FAILED confers nothing: its
    # paths land under 'decayed' (unless newer live evidence holds them).
    candidates.sort(key=lambda c: c[0], reverse=True)
    decay_check: dict = {}
    decayed_rows: list = []
    for created, kind, holder, path, eid in candidates:
        if eid not in decay_check:
            decay_check[eid] = _failed_latest_retest(eid)
        if decay_check[eid]:
            decayed_rows.append((path, holder, kind, eid, decay_check[eid]))
            continue
        claim(path, holder, kind, eid, created)
    decayed: dict = {}
    for path, holder, kind, eid, ret_eid in decayed_rows:
        if path not in files and path not in decayed:
            decayed[path] = {"holder": holder, "kind": kind, "eid": eid,
                             "failed_retention_eid": ret_eid}

    holders: dict = {}
    for row in files.values():
        holders[row["holder"]] = holders.get(row["holder"], 0) + 1
    note = ("holdership = the latest COMPLETE attestation or PASSED "
            "comprehension receipt per file; partial or failed evidence "
            "confers nothing; a failed unaided retest decays the row into "
            "'decayed' with the failing retention receipt named")
    if not files:
        note = "no checked evidence yet; " + note
    return {"schema": SCHEMA, "files": files, "decayed": decayed,
            "holders": holders, "note": note}
