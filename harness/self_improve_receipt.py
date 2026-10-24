"""self_improve_receipt.py -- the receipt every harness-edit decision carries.

A receipt binds four things a reviewer needs to accept or refuse an edit
without trusting the loop that made it:

  1. the diff, from the incumbent to what was adopted, with both digests;
  2. the contrast that chose it: the finals, the selector's scores and reason,
     and the stages that proposed each component;
  3. the held-out effect: paired means, the interval, its method and level, and
     the digest of the graded set;
  4. the decision, re-derivable from (3) and the recorded policy.

verify_edit_receipt re-derives the seal, the decision, and, when the trees are
supplied, the digests and the diff. A receipt whose numbers do not support its
own decision is INCONSISTENT even when its seal matches.
"""
from __future__ import annotations

from typing import Any

from . import self_improve_tree as st
from .evidence_json import canonical_sha256
from .scope import scope_list

SCHEMA_V2 = "flywheel.harness-edit-receipt/v2"
SCHEMA = "flywheel.harness-edit-receipt/v3"  # v3 names `scope`
SCHEMAS = ("flywheel.harness-edit-receipt/v1", SCHEMA_V2, SCHEMA)
MATCH, TAMPERED, INCONSISTENT = "MATCH", "TAMPERED", "INCONSISTENT"


def _contrast(run: Any) -> dict:
    return {"task_id": run.task_id, "mode": run.mode, "k": run.k, "finals": run.finals,
            "chosen": run.chosen, "why": run.why[:600], "scores": run.scores,
            "stages": [{k: s.get(k) for k in ("label", "dim", "components", "fell_back")}
                       for s in run.stages], "budget": dict(run.budget)}


def _attribution(rows: list[dict]) -> list[dict]:
    return [{"unit": r.get("unit", r["component"]), "component": r["component"],
             "verification_surface": r["verification_surface"],
             "kept": r["kept"], "point": r["effect"]["point"],
             "interval": r["effect"]["interval"]} for r in rows]


def build_edit_receipt(*, parent: st.Tree, candidate: st.Tree, run: Any, gate: dict,
                       provenance: dict | None = None) -> dict:
    """Seal one gate decision about one task-level candidate."""
    adopted = gate["tree"]
    body = {
        "schema": SCHEMA,
        "decision": gate["decision"],
        "reason": gate["reason"],
        "parent_digest": st.digest(parent),
        "candidate_digest": st.digest(candidate),
        "adopted_digest": st.digest(adopted),
        "candidate_components": st.changed_components(parent, candidate),
        "adopted_components": list(gate["adopted_components"]),
        "adopted_units": list(gate.get("adopted_units", gate["adopted_components"])),
        "granularity": gate.get("granularity", "file"),
        "diff": st.unified_diff(parent, adopted),
        "contrast": _contrast(run),
        "heldout": gate["heldout"],
        "attribution": _attribution(gate["attribution"]),
        "policy": gate["policy"],
        "provenance": dict(provenance or {}),
        "scope": scope_list(gate),
    }
    body["seal_sha256"] = canonical_sha256(body)
    return body


def _decision_supported(r: dict) -> bool:
    eff, pol = r.get("heldout"), r.get("policy", {})
    if r.get("decision") == "REJECT":
        return r.get("adopted_digest") == r.get("parent_digest")
    if not eff or r.get("decision") != "ADOPT" or not r.get("adopted_components"):
        return False
    if "adopted_units" in r:
        key, adopted = "unit", r["adopted_units"]
    else:
        key, adopted = "component", r["adopted_components"]
    kept = {a.get(key) for a in r.get("attribution", []) if a["kept"]}
    if r.get("attribution") and not set(adopted) <= kept:
        return False
    return (eff["point"] > pol.get("min_point", 0.0)
            and eff["interval"][0] >= pol.get("min_lower", 0.0))


def verify_edit_receipt(receipt: dict, *, parent: st.Tree | None = None,
                        adopted: st.Tree | None = None) -> dict:
    """Return {verdict, detail}: MATCH, TAMPERED or INCONSISTENT."""
    if receipt.get("schema") not in SCHEMAS:
        return {"verdict": TAMPERED, "detail": "unknown schema"}
    body = {k: v for k, v in receipt.items() if k != "seal_sha256"}
    if canonical_sha256(body) != receipt.get("seal_sha256"):
        return {"verdict": TAMPERED, "detail": "seal does not match the body"}
    if parent is not None and st.digest(parent) != receipt["parent_digest"]:
        return {"verdict": TAMPERED, "detail": "parent tree does not match its digest"}
    if adopted is not None:
        if st.digest(adopted) != receipt["adopted_digest"]:
            return {"verdict": TAMPERED, "detail": "adopted tree does not match its digest"}
        if parent is not None and st.unified_diff(parent, adopted) != receipt["diff"]:
            return {"verdict": TAMPERED, "detail": "diff does not reproduce from the trees"}
    if not _decision_supported(receipt):
        return {"verdict": INCONSISTENT,
                "detail": "the recorded numbers do not support the recorded decision"}
    return {"verdict": MATCH, "detail": "seal, digests and decision re-derive"}
