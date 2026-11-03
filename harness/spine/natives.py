"""natives.py -- recheck three tools' own receipts, from their published formats.

Each checker recomputes the tool's own content address or seal, by the recipe
the tool documents, and derives the verdict the payload carries. None imports
the tool. The recipes are interfaces, written from:

  emet      SPEC.md section 17 (emet-witness-receipt/v1). receipt_id is sha256
            of json.dumps(body, sort_keys=True, ensure_ascii=True) with
            receipt_id, signature and witness left out.
  crucible  crucible.assessment/1, src/crucible/assess.py: verdict_seal and
            measurement_seal over named row fields, sorted; seal over the
            record fields. Status from deviation and tolerance by verdict_for
            rule 5. Spine status by src/crucible/interop.py.
  gather    gather.digest/1, src/gather/digest.py: seal over the sorted
            receipt projections, availability and storage folded in when set.

A checker returns (intact, source_verdict, detail). intact is None when the
payload cannot be read at all.
"""
from __future__ import annotations

import hashlib
import json
import math

from .vocab import INTEGRITY, ORGAN_BUNDLE

EMET = "emet-witness-receipt/v1"
CRUCIBLE = "crucible.assessment/1"
GATHER = "gather.digest/1"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _py_json(value, *, ascii_only: bool) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=ascii_only)


# -- emet ---------------------------------------------------------------------

_EMET_UNADDRESSED = ("receipt_id", "signature", "witness")
_EMET_TERMS = ("MATCH", "DRIFT", "UNVERIFIABLE")


def _emet_verdict(rows) -> str:
    terms = [r.get("verdict") for r in rows]
    if not terms or any(t not in _EMET_TERMS for t in terms):
        return "UNVERIFIABLE"
    if "DRIFT" in terms:
        return "DRIFT"
    return "MATCH" if all(t == "MATCH" for t in terms) else "UNVERIFIABLE"


def check_emet(receipt):
    if not isinstance(receipt, dict) or receipt.get("format") != EMET:
        return None, None, f"not an {EMET} receipt"
    rows = receipt.get("verdict_record")
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return None, None, "verdict_record is not a list of objects"
    body = {k: v for k, v in receipt.items() if k not in _EMET_UNADDRESSED}
    if _sha(_py_json(body, ascii_only=True)) != receipt.get("receipt_id"):
        return False, None, "receipt_id does not re-derive (RECEIPT_TAMPERED)"
    if receipt.get("signature") is not None:
        return None, None, "signed receipt and no key here (RECEIPT_UNVERIFIABLE)"
    return True, _emet_verdict(rows), "receipt_id re-derives (RECEIPT_VALID)"


# -- crucible -----------------------------------------------------------------

_VSEAL = ("claim_id", "claim_sha256", "status", "deviation", "tolerance",
          "margin", "method", "grounds", "disposition")
_MSEAL = ("claim_id", "claim_sha256", "deviation", "tolerance", "method",
          "measured_at", "evidence")
_RECORD = ("started_at", "thesis_id", "thesis_seal", "claims", "match",
           "drift", "unverifiable", "verdict_seal", "measurement_seal",
           "disposition", "stored")


def _seal_rows(rows, fields) -> str:
    objs = [{k: r.get(k) for k in fields} for r in rows]
    objs.sort(key=lambda d: _py_json(d, ascii_only=False))
    return _sha(_py_json(objs, ascii_only=False))


def _status_follows(row) -> bool:
    """MATCH and DRIFT rows must follow from their own deviation and tolerance."""
    status, dev, tol = row.get("status"), row.get("deviation"), row.get("tolerance")
    if status == "UNVERIFIABLE":
        return True
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
               and math.isfinite(x) for x in (dev, tol)) or dev < 0 or tol <= 0:
        return False
    return (status == "MATCH") == ((tol - dev) / tol >= 0.0)


def _crucible_status(match: int, drift: int, unverifiable: int) -> str:
    if drift > 0:
        return "fail"
    if match > 0 and unverifiable == 0:
        return "pass"
    if unverifiable > 0 and match == 0:
        return "unverified"
    return "warn" if match > 0 else "unknown"


def check_crucible(a):
    if not isinstance(a, dict) or any(k not in a for k in _RECORD + ("seal",)):
        return None, None, f"not a {CRUCIBLE} record"
    verdicts, measurements = a.get("verdicts"), a.get("measurements")
    if not isinstance(verdicts, list) or not isinstance(measurements, list):
        return None, None, "verdicts and measurements must be lists"
    counts = {s: sum(1 for r in verdicts if r.get("status") == s)
              for s in ("MATCH", "DRIFT", "UNVERIFIABLE")}
    if (sum(counts.values()) != len(verdicts) or a["claims"] != len(verdicts)
            or (a["match"], a["drift"], a["unverifiable"])
            != (counts["MATCH"], counts["DRIFT"], counts["UNVERIFIABLE"])):
        return False, None, "verdict counts do not match the verdict rows"
    mfields = _MSEAL + ("recheck",) if any("recheck" in r for r in measurements) else _MSEAL
    if (_seal_rows(verdicts, _VSEAL) != a["verdict_seal"]
            or _seal_rows(measurements, mfields) != a["measurement_seal"]):
        return False, None, "verdict_seal or measurement_seal does not re-derive"
    if _sha(_py_json({k: a[k] for k in _RECORD}, ascii_only=False)) != a["seal"]:
        return False, None, "record seal does not re-derive"
    if not all(_status_follows(r) for r in verdicts):
        return False, None, "a stored status does not follow from its deviation"
    status = _crucible_status(a["match"], a["drift"], a["unverifiable"])
    return True, status, "seals re-derive and statuses follow from deviations"


# -- gather -------------------------------------------------------------------

_GATHER_FIELDS = ("kind", "id", "title", "source", "ref", "method", "sha256")


def _gather_seal(receipts) -> str:
    objs = []
    for r in receipts:
        o = {k: r[k] for k in _GATHER_FIELDS}
        o["derived_from"] = list(r.get("derived_from") or [])
        for extra in ("availability", "storage"):
            if r.get(extra) is not None:
                o[extra] = r[extra]
        objs.append(o)
    objs.sort(key=lambda d: _py_json(d, ascii_only=False))
    return _sha(_py_json(objs, ascii_only=False))


def check_gather(d):
    if not isinstance(d, dict) or not isinstance(d.get("receipts"), list):
        return None, None, f"not a {GATHER} digest"
    if not all(isinstance(r, dict) and all(k in r for k in _GATHER_FIELDS)
               for r in d["receipts"]):
        return None, None, "a receipt is missing a required field"
    if _gather_seal(d["receipts"]) != d.get("seal"):
        return False, "DRIFT", "digest seal does not re-derive"
    return True, "MATCH", "digest seal re-derives"


# -- registry -----------------------------------------------------------------

# source_schema -> (tool, vocabulary, checker, scope)
NATIVE = {
    EMET: ("emet", INTEGRITY, check_emet,
           "The subject files hashed to the recorded digests when emet issued "
           "the receipt; the receipt's content address re-derives."),
    CRUCIBLE: ("crucible", ORGAN_BUNDLE, check_crucible,
               "Each claim's stored verdict follows from its stored deviation "
               "and tolerance, and the assessment seals re-derive."),
    GATHER: ("gather", INTEGRITY, check_gather,
             "The digest's seal covers each item's content hash and how it "
             "arrived, and re-derives from the receipts it lists."),
}


def recheck(source_schema: str, payload):
    """(intact, source_verdict, detail) from the named native checker."""
    entry = NATIVE.get(source_schema)
    if entry is None:
        return None, None, f"no native checker for {source_schema!r}"
    return entry[2](payload)
