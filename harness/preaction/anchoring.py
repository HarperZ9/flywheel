"""anchoring.py -- what a store's chain is anchored to, and the verdict for none.

A store whose seals and links all hold is internally consistent. That is all
it is when no trust root is pinned: the seals are unkeyed sha256, so anyone who
can write the store can rewrite it and recompute every seal. ``verify_store``
therefore never reports MATCH for an unanchored store. It reports UNANCHORED,
with the internal result beside it.

A trust root is the separate signer's public key, pinned by the verifier from
outside the store (a flag or the owner's environment, never a file in the
store). With it pinned, every record must carry an attestation from that key,
for this store, at its own sequence number and seal. A signed head from the
signer, when supplied, catches a store truncated after signing.
"""
from __future__ import annotations

from ..signer import statement as st

UNANCHORED = "UNANCHORED"
UNANCHORED_NOTE = ("No trust root is pinned. The seals are unkeyed sha256, so this "
                   "result shows only that the store is internally consistent; "
                   "anyone who can write the store could have produced it.")
SAME_IDENTITY_NOTE = ("The signer ran under the same identity as the agent for at "
                      "least one record, so the agent's identity could read the key "
                      "and forge those records.")


def _record_findings(rec: dict, store: str, root: bytes) -> list:
    att = rec.get("attestation")
    src = rec.get("source", "")
    if att is None:
        return [{"cause": "UNSIGNED_RECORD", "source": src}]
    ok, why = st.check(att, root, st.ATTESTATION_SCHEMA)
    if not ok:
        return [{"cause": "ATTESTATION_INVALID", "source": src, "detail": why}]
    want = (store, rec.get("store_seq"), rec.get("prev_record_sha256", ""),
            rec.get("seal", {}).get("hex", ""))
    got = (att.get("store"), att.get("seq"), att.get("prev"), att.get("seal"))
    if want != got:
        return [{"cause": "ATTESTATION_DOES_NOT_MATCH_RECORD", "source": src}]
    return []


def _head_findings(head, recs: list, store: str, root: bytes) -> list:
    ok, why = st.check(head, root, st.HEAD_SCHEMA)
    if not ok:
        return [{"cause": "SIGNER_HEAD_INVALID", "detail": why}]
    if head.get("store") != store:
        return [{"cause": "SIGNER_HEAD_FOR_ANOTHER_STORE"}]
    seq = int(head.get("seq", 0))
    by_seq = {int(r.get("store_seq", 0)): r.get("seal", {}).get("hex", "") for r in recs}
    if seq and seq not in by_seq:
        return [{"cause": "TRUNCATED_AFTER_SIGNING", "signed_seq": seq,
                 "store_records": len(recs)}]
    if seq and by_seq[seq] != head.get("seal"):
        return [{"cause": "SIGNER_HEAD_SEAL_DIFFERS", "signed_seq": seq}]
    return []


def check(recs: list, store: str, trust_root_hex: str = "", signer_head=None) -> dict:
    """Findings and labels from the trust root. Empty findings with no root
    still means UNANCHORED; see ``final_verdict``."""
    if not trust_root_hex:
        return {"anchored": False, "findings": [], "signer_isolation": [],
                "notes": [UNANCHORED_NOTE]}
    root = bytes.fromhex(trust_root_hex)
    findings, modes = [], set()
    for rec in recs:
        findings += _record_findings(rec, store, root)
        if isinstance(rec.get("attestation"), dict):
            modes.add(st.isolation_of(rec["attestation"]))
    if signer_head is not None:
        findings += _head_findings(signer_head, recs, store, root)
    notes = [SAME_IDENTITY_NOTE] if modes & {st.SAME, st.UNATTESTED} else []
    return {"anchored": True, "findings": findings, "signer_isolation": sorted(modes),
            "rewinds": (signer_head or {}).get("rewinds", []), "notes": notes,
            "truncation_checked": signer_head is not None}


def final_verdict(internal: str, anchored: bool) -> str:
    """A pass needs a trust root. DRIFT and UNVERIFIABLE stand as they are."""
    if internal == "MATCH" and not anchored:
        return UNANCHORED
    return internal
