"""public_anchor.py -- check a store against the signer heads anchored in public logs.

The signer's key lives on the host. An attacker who owns the host can sign a
replacement history and a fresh head for it, and every signature checks. What
that attacker cannot change is a head already logged in Sigstore's Rekor and
committed to Bitcoin through OpenTimestamps. This module reads the anchor
receipts the signer's anchor job wrote (harness/signer/anchor_job.py) and holds
the store to every anchored head:

  * a receipt counts only when its head verifies under the pinned trust root
    and its Rekor record verifies offline under Rekor's pinned key;
  * the store must hold the anchored seal at the anchored sequence number, or
    the verifier reports ANCHORED_HEAD_DISAGREES (DRIFT);
  * records after the newest valid anchor are counted as ``unanchored``. They
    are reported, never passed: status ``PARTIAL``, not ``ANCHORED``.

With ``online``, the verifier also lists every Rekor entry under the signer's
key. An entry with no local receipt means a head was logged that the receipts
do not account for, the trace a host attacker leaves by deleting receipts.
Standard library only, so a stranger can run it.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from .. import ots_verify, rekor_verify
from ..receipt_fields import canonical
from ..signer import statement as st

INDEX_PATH = "/api/v1/index/retrieve"
NOT_CHECKED_NOTE = ("No anchors directory was given, so the store was not held to any "
                    "publicly anchored head. A compromised host could rewrite it.")


def store_key(store: str) -> str:
    return hashlib.sha256(store.encode("utf-8")).hexdigest()[:16]


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ots_state(path: Path, data: bytes) -> tuple[str, list]:
    proof = path.with_suffix(".ots")
    if not proof.exists():
        return "absent", []
    res = ots_verify.verify(proof.read_bytes(), hashlib.sha256(data).digest())
    if str(res.get("reason", "")).startswith("digest_mismatch"):
        return "other-bytes", [{"cause": "OTS_PROOF_FOR_OTHER_BYTES", "receipt": path.name}]
    if res.get("bitcoin"):
        return "bitcoin", []
    return ("pending" if res.get("pending") else "unreadable"), []


def _receipt(path: Path, store: str, root: bytes, rekor_check) -> tuple[dict | None, list]:
    """(anchor, findings) for one receipt. ``anchor`` is None when it does not count."""
    rec = _load(path)
    head = (rec or {}).get("signed_head")
    if not isinstance(head, dict):
        return None, [{"cause": "ANCHOR_RECEIPT_INVALID", "receipt": path.name,
                       "detail": "unreadable"}]
    ok, why = st.check(head, root, st.HEAD_SCHEMA)
    if not ok:
        return None, [{"cause": "ANCHOR_RECEIPT_INVALID", "receipt": path.name,
                       "detail": f"head: {why}"}]
    if head.get("store") != store:
        return None, [{"cause": "ANCHOR_RECEIPT_FOR_ANOTHER_STORE", "receipt": path.name}]
    data = canonical(head).encode()
    rk = rekor_check(rec.get("rekor") or {}, data, root)
    if not rk["ok"]:
        return None, [{"cause": "ANCHOR_RECEIPT_INVALID", "receipt": path.name,
                       "detail": f"rekor: {rk['reasons']}"}]
    ots, findings = _ots_state(path, data)
    return {"seq": int(head.get("seq", 0)), "seal": head.get("seal", ""),
            "log_index": rk.get("log_index"), "integrated_time": rk.get("integrated_time"),
            "uuid": (rec.get("rekor") or {}).get("uuid", ""), "ots": ots,
            "receipt": path.name}, findings


def _against_store(anchor: dict, by_seq: dict) -> list:
    seq = anchor["seq"]
    if seq and seq not in by_seq:
        return [{"cause": "STORE_SHORTER_THAN_ANCHORED_HEAD", "anchored_seq": seq,
                 "log_index": anchor["log_index"]}]
    if seq and by_seq[seq] != anchor["seal"]:
        return [{"cause": "ANCHORED_HEAD_DISAGREES", "anchored_seq": seq,
                 "log_index": anchor["log_index"]}]
    return []


def _online(root: bytes, anchors_dir: Path, request) -> tuple[dict, list]:
    """Every Rekor entry under the signer's key must have a local receipt."""
    pem = rekor_verify.ed25519_public_pem(root)
    body = json.dumps({"publicKey": {"format": "x509", "content":
                       base64.b64encode(pem.encode()).decode()}}).encode()
    try:
        status, reply, _ = request("POST", rekor_verify.REKOR_URL + INDEX_PATH, body=body)
        logged = json.loads(reply) if status == 200 else None
    except (RuntimeError, OSError, ValueError) as exc:
        return {"checked": False, "error": f"{type(exc).__name__}: {exc}"}, []
    if not isinstance(logged, list):
        return {"checked": False, "error": f"Rekor index answered {status}"}, []
    known = set()
    for path in Path(anchors_dir).glob("*/head-*.json"):
        uuid = ((_load(path) or {}).get("rekor") or {}).get("uuid", "")
        if uuid:
            known.add(uuid[-64:])
    missing = sorted(u for u in logged if str(u)[-64:] not in known)
    findings = ([{"cause": "ANCHORED_HEAD_WITHOUT_RECEIPT", "uuids": missing}]
                if missing else [])
    return {"checked": True, "rekor_entries": len(logged), "without_receipt": missing}, findings


def check(recs: list, store: str, trust_root_hex: str, anchors_dir, *,
          rekor_check=None, online_request=None) -> dict:
    """Findings and the ``public_anchor`` report for one store. ``rekor_check``
    defaults to the offline Rekor verifier under Rekor's pinned key."""
    rekor_check = rekor_check or rekor_verify.verify_record
    if not anchors_dir or not trust_root_hex:
        why = NOT_CHECKED_NOTE if not anchors_dir else (
            "No trust root is pinned, so no anchored head can be checked.")
        return {"report": {"status": "NOT_CHECKED"}, "findings": [], "notes": [why]}
    root = bytes.fromhex(trust_root_hex)
    by_seq = {int(r.get("store_seq", 0)): r.get("seal", {}).get("hex", "") for r in recs}
    findings, anchors = [], []
    for path in sorted((Path(anchors_dir) / store_key(store)).glob("head-*.json")):
        anchor, found = _receipt(path, store, root, rekor_check)
        findings += found
        if anchor is not None:
            anchors.append(anchor)
            findings += _against_store(anchor, by_seq)
    through = max((a["seq"] for a in anchors), default=0)
    unanchored = sum(1 for s in by_seq if s > through)
    status = "NONE" if not anchors else ("ANCHORED" if unanchored == 0 else "PARTIAL")
    report = {"status": status, "anchored_through_seq": through,
              "unanchored_records": unanchored, "anchors": anchors}
    notes = []
    if status == "NONE":
        notes.append("No valid public anchor covers this store. A compromised host "
                     "could rewrite all of it.")
    elif status == "PARTIAL":
        notes.append(f"{unanchored} record(s) after seq {through} are not publicly "
                     "anchored yet. A compromised host could rewrite those.")
    if online_request is not None:
        report["online"], more = _online(root, Path(anchors_dir), online_request)
        findings += more
        if not report["online"]["checked"]:
            notes.append("The online check of Rekor did not complete; receipts deleted "
                         "from this host would go unnoticed.")
    return {"report": report, "findings": findings, "notes": notes}
