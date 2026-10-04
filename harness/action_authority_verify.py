"""action_authority_verify.py -- re-derive a receipt's authority instead of trusting it.

The agent-side process writes the receipt, so it can write any basis it likes.
The verifier therefore recomputes the block from its elements:

  * a ``policy:machine`` element counts only when its statement verifies under
    the trust root the verifier pinned, was signed by a signer that measured a
    separate identity, and covers this receipt's tool and argument digest, with
    the decision the signed verdict implies. Anything less is re-labelled
    ``policy:self``: a rule nothing outside the agent enforced;
  * an ``intent`` element is re-classified from its stored words, so a plan
    restatement filed as intent comes back as scope;
  * the block is then resolved again, and a recorded basis, decision or
    verdict that differs from the re-derived one is AUTHORITY_OVERSTATED.

``verify_action`` joins this to the receipt's own seal check. Its verdict is
MATCH only when the seal holds and the re-derived authority is a PASS.
"""
from __future__ import annotations

from . import action_authority as au
from .signer import statement as st
from .signer.policy import POLICY_SCHEMA
from .tool_call_receipt import verify_receipt


def _machine_problem(element: dict, receipt: dict, root: bytes | None) -> str:
    stmt = element.get("statement")
    if root is None:
        return "no trust root pinned"
    ok, why = st.check(stmt, root, POLICY_SCHEMA)
    if not ok:
        return f"policy statement does not verify: {why}"
    if st.isolation_of(stmt) != st.SEPARATE:
        return f"signer isolation is {st.isolation_of(stmt)}"
    if stmt.get("tool") != receipt.get("tool"):
        return "policy statement covers another tool"
    if stmt.get("args_sha256") != (receipt.get("args") or {}).get("sha256"):
        return "policy statement covers other arguments"
    want = au.ALLOW if stmt.get("verdict") == "ALLOW" else au.DENY
    if element.get("decision") != want:
        return "recorded decision differs from the signed verdict"
    return ""


def _rederive_element(element: dict, receipt: dict, root: bytes | None) -> tuple:
    """(element as it verifies, reason it was downgraded or '')."""
    basis = element.get("basis")
    if basis == au.MACHINE:
        why = _machine_problem(element, receipt, root)
        if why:
            return dict(element, basis=au.SELF, downgraded=why), why
    if basis == au.INTENT:
        got, why = au.classify_confirmation(
            element.get("quote", ""), object_name=element.get("object", ""),
            fact=element.get("fact", ""), plan_summary=element.get("plan_summary", ""))
        if got != au.INTENT:
            return dict(element, basis=got, downgraded=why), why
    if basis not in au.STRENGTH or element.get("decision") not in (au.ALLOW, au.DENY):
        return None, f"unknown basis or decision: {basis!r}"
    return element, ""


def verify_authority(receipt: dict, trust_root_hex: str = "") -> dict:
    """The re-derived authority of one receipt, and findings where the
    recorded block claims more than its evidence supports."""
    root = bytes.fromhex(trust_root_hex) if trust_root_hex else None
    block = receipt.get("authority")
    if not isinstance(block, dict):
        out = au.resolve([])
        return {**out, "findings": [{"cause": "NO_AUTHORITY_RECORDED"}]}
    findings, kept = [], []
    for element in block.get("elements", []):
        got, why = _rederive_element(element, receipt, root)
        if why:
            findings.append({"cause": "AUTHORITY_DOWNGRADED", "from": element.get("basis"),
                             "detail": why})
        if got is not None:
            kept.append(got)
    out = au.resolve(kept)
    for key in ("basis", "decision", "verdict"):
        if block.get(key) != out[key]:
            findings.append({"cause": "AUTHORITY_OVERSTATED", "field": key,
                             "recorded": block.get(key), "rederived": out[key]})
    if out["basis"] == au.NONE:
        findings.append({"cause": "NO_AUTHORITY_RECORDED"})
    return {**out, "findings": findings}


def verify_action(receipt: dict, trust_root_hex: str = "") -> dict:
    """Seal plus authority. MATCH only for an intact receipt whose re-derived
    authority is a PASS; FINDING or UNENFORCED otherwise; TAMPERED on a seal."""
    sealed = verify_receipt(receipt)
    if sealed.get("verdict") != "MATCH":
        return {"verdict": "TAMPERED", "seal": sealed, "authority": None}
    auth = verify_authority(receipt, trust_root_hex)
    verdict = {au.PASS: "MATCH", au.UNENFORCED: au.UNENFORCED}.get(auth["verdict"], au.FINDING)
    if auth["findings"] and verdict == "MATCH":
        verdict = au.FINDING
    return {"verdict": verdict, "seal": sealed, "authority": auth}
