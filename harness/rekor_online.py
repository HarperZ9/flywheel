"""rekor_online.py -- the online half of a Rekor anchor check.

The offline check (`rekor_verify.verify_record`) shows the stored entry, its
signed timestamp and its inclusion proof all verify under the pinned Rekor key.
What it cannot show is that the log still holds the entry and that the
checkpoint in the record is part of the same log everyone else sees today. This
module asks Rekor for both:

  1. it refetches the entry by UUID and requires the same body, integrated
     time, log ID and log index, then runs the full offline check on the fresh
     copy (fresh inclusion proof, fresh checkpoint);
  2. it fetches a consistency proof from the stored checkpoint's tree size to
     the fresh one, and checks it (RFC 9162 section 2.1.4.2), so the tree the
     record was proven against is a prefix of today's tree.

Rekor's answers are checked, not trusted: every signature and proof is verified
here under the pinned key. Like the offline check, it raises nothing.
"""
from __future__ import annotations

import hashlib
import json

from . import rekor_submit, rekor_verify


def _node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def verify_consistency(size1: int, size2: int, proof: list[bytes],
                       root1: bytes, root2: bytes) -> bool:
    """RFC 9162 section 2.1.4.2: the size1 tree is a prefix of the size2 tree."""
    if size1 == size2:
        return not proof and root1 == root2
    if not 0 < size1 < size2 or not proof and size1 & (size1 - 1):
        return False
    if size1 & (size1 - 1) == 0:
        proof = [root1] + list(proof)
    fn, sn = size1 - 1, size2 - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = proof[0]
    for c in proof[1:]:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr, sr = _node(c, fr), _node(c, sr)
            while fn and not fn & 1:
                fn >>= 1
                sn >>= 1
        else:
            sr = _node(sr, c)
        fn >>= 1
        sn >>= 1
    return sn == 0 and fr == root1 and sr == root2


def _tree_id(checkpoint: dict) -> str:
    return checkpoint["origin"][len(rekor_verify.CHECKPOINT_ORIGIN_PREFIX):]


def verify_online(record: dict, artifact: bytes, public_key: bytes, request, *,
                  base_url: str = rekor_verify.REKOR_URL) -> dict:
    """Refetch and reprove a stored anchor. Returns {"ok", "reasons", ...}."""
    reasons: list[str] = []
    stored = (record or {}).get("entry") or {}
    try:
        uuid, fresh = rekor_submit.fetch(record["uuid"], request, base_url=base_url)
    except (KeyError, rekor_submit.RekorError, ValueError) as e:
        return {"ok": False, "reasons": [f"REFETCH_FAILED: {e}"]}
    for field in ("body", "integratedTime", "logID", "logIndex"):
        if fresh.get(field) != stored.get(field):
            reasons.append(f"REFETCHED_{field.upper()}_DIFFERS")
    offline = rekor_verify.verify_record({"entry": fresh}, artifact, public_key)
    reasons += [f"FRESH_{r}" for r in offline["reasons"]]
    reasons += _consistency_reasons(stored, fresh, request, base_url)
    return {"ok": not reasons, "reasons": reasons, "uuid": uuid,
            "log_index": fresh.get("logIndex"),
            "integrated_time": fresh.get("integratedTime")}


def _consistency_reasons(stored: dict, fresh: dict, request, base_url: str) -> list[str]:
    old = rekor_verify.parse_checkpoint(
        ((stored.get("verification") or {}).get("inclusionProof") or {}).get("checkpoint", ""))
    new = rekor_verify.parse_checkpoint(
        ((fresh.get("verification") or {}).get("inclusionProof") or {}).get("checkpoint", ""))
    if old is None or new is None:
        return ["CHECKPOINT_UNREADABLE"]
    if old["origin"] != new["origin"]:
        return ["CHECKPOINT_ORIGIN_CHANGED"]
    if old["size"] == new["size"]:
        return [] if old["root"] == new["root"] else ["SAME_SIZE_DIFFERENT_ROOT"]
    url = (f"{base_url}/api/v1/log/proof?firstSize={old['size']}"
           f"&lastSize={new['size']}&treeID={_tree_id(old)}")
    try:
        status, reply, _ = request("GET", url)
        data = json.loads(reply) if status == 200 else None
        hashes = [bytes.fromhex(h) for h in data["hashes"]]
    except (rekor_submit.RekorError, KeyError, TypeError, ValueError):
        return ["CONSISTENCY_PROOF_UNAVAILABLE"]
    # The endpoint's own `rootHash` is the log's latest root, which has usually
    # moved on by the time it answers, so it is not used. The proof is checked
    # against the two signed checkpoints instead, both verified under the pin.
    if not verify_consistency(old["size"], new["size"], hashes, old["root"], new["root"]):
        return ["CONSISTENCY_PROOF_INVALID"]
    return []
