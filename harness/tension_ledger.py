"""tension_ledger.py -- measurement tension as a first-class receipt.

Two measurements of the same quantity, each carrying a frozen source
hash, become one ledger entry with an honest verdict decided by the
field's own metric: the sigma distance |a - b| / sqrt(sa^2 + sb^2).
TENSION above 1.96 sigma, CONSISTENT at or below, and UNVERIFIABLE when
the pair cannot be judged at all (no frozen source, non-positive sigma,
mismatched units). The 95% intervals ride along as information; they do
not judge, because interval overlap under-calls disagreement (two 95%
intervals still overlap out to ~2.77 sigma, the CI-overlap fallacy).
An unverifiable pair is never banked: no receipt, no accept, for
physics exactly as for code. The ledger asserts nothing about which
measurement is right -- it keeps the disagreement re-checkable.
"""
from __future__ import annotations

import math

SCHEMA = "flywheel.tension/v1"
_Z95 = 1.96


def _check_side(m: dict) -> "str | None":
    if not isinstance(m, dict):
        return "each side must be a measurement object"
    if not str(m.get("label", "")).strip():
        return "each side needs a 'label'"
    if not isinstance(m.get("value"), (int, float)):
        return "each side needs a numeric 'value'"
    if not isinstance(m.get("sigma"), (int, float)) or m["sigma"] <= 0:
        return "each side needs a positive 'sigma'"
    sha = str(m.get("source_sha256", "")).lower()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        return "each side needs a frozen source (source_sha256, 64 hex)"
    return None


def _side_doc(m: dict) -> dict:
    v, s = float(m["value"]), float(m["sigma"])
    return {"label": m["label"], "value": v, "sigma": s,
            "unit": str(m.get("unit", "")),
            "interval_95": [v - _Z95 * s, v + _Z95 * s],
            "source_sha256": m["source_sha256"]}


def tension_entry(a: dict, b: dict) -> dict:
    """Judge one pair. The verdict is earned or withheld, never guessed."""
    for side in (a, b):
        reason = _check_side(side)
        if reason:
            return {"schema": SCHEMA, "verdict": "unverifiable",
                    "reason": reason}
    if str(a.get("unit", "")) != str(b.get("unit", "")):
        return {"schema": SCHEMA, "verdict": "unverifiable",
                "reason": "unit mismatch: "
                          f"{a.get('unit')!r} vs {b.get('unit')!r}"}
    da, db = _side_doc(a), _side_doc(b)
    sigma_distance = (abs(da["value"] - db["value"])
                      / math.sqrt(da["sigma"] ** 2 + db["sigma"] ** 2))
    overlap = (da["interval_95"][0] <= db["interval_95"][1]
               and db["interval_95"][0] <= da["interval_95"][1])
    return {"schema": SCHEMA, "a": da, "b": db,
            "sigma_distance": round(sigma_distance, 4),
            "overlap_95": overlap,
            "verdict": "tension" if sigma_distance > _Z95 else "consistent",
            "note": "the ledger asserts nothing about which side is right; "
                    "it keeps the disagreement re-checkable via the frozen "
                    "sources"}


def bank_tension(a: dict, b: dict) -> dict:
    """Bank a judged pair. Unverifiable pairs are refused, not stored."""
    from .store import put_entity
    e = tension_entry(a, b)
    if e["verdict"] == "unverifiable":
        return {"error": f"unverifiable pair not banked: {e['reason']}"}
    stored = put_entity("tension", e)
    return {**e, "stored": stored.get("eid", ""),
            "chain_hash": stored.get("chain_hash", "")}


def tension_ledger() -> dict:
    """Every banked tension, newest first, with the split that matters."""
    from .store import get_entity, query_entities
    entries = []
    for meta in query_entities(kind="tension", limit=500):
        e = get_entity(meta["eid"])
        if e:
            entries.append({**e["data"], "eid": meta["eid"]})
    return {"schema": "flywheel.tension-ledger/v1", "count": len(entries),
            "tensions": sum(1 for e in entries
                            if e.get("verdict") == "tension"),
            "entries": entries}
