"""anchor_job.py -- put the signer's heads into two public logs, on a cadence.

A head signed on the host proves nothing once the host is compromised: whoever
holds the key can sign a replacement history and a fresh head for it. A head
logged in Sigstore's Rekor and committed to Bitcoin through OpenTimestamps is
outside the host's reach, so a rewritten history that disagrees with it fails
(harness/preaction/public_anchor.py).

Run as the signer identity, from a timer the setup scripts install:

    python -m harness.signer anchor --home <signer home> --out <anchors dir>

For every store in the journal whose head moved at least ``--min-new`` records
past its last anchor, the job signs a head, logs its SHA-512 and an Ed25519ph
signature in Rekor under the signer's own key, submits its SHA-256 to
OpenTimestamps, and writes a receipt to ``<out>/<store key>/``. Only hashes, the
signature and the public key leave the machine. Each run also tries to upgrade
pending OpenTimestamps proofs. The records signed since the last anchor stay
unanchored until the next run: the timer period is the exposure window.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .. import rekor_submit, rekor_verify
from ..preaction.public_anchor import store_key
from ..receipt_fields import canonical
from . import keys
from .server import Signer

RECEIPT_SCHEMA = "flywheel.signer-anchor/v1"
JOB_ISOLATION = {"mode": "unattested", "signer": "self", "client": "anchor-job"}




def head_bytes(head: dict) -> bytes:
    """The bytes both logs cover: the signed head in canonical JSON."""
    return canonical(head).encode()


def receipts(out: Path, store: str) -> list:
    """(path, receipt) for every receipt of ``store``, oldest seq first."""
    found = []
    for p in sorted((Path(out) / store_key(store)).glob("head-*.json")):
        try:
            found.append((p, json.loads(p.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return sorted(found, key=lambda pr: int(pr[1].get("signed_head", {}).get("seq", 0)))


def _last_seq(out: Path, store: str) -> int:
    seqs = [int(r.get("signed_head", {}).get("seq", 0)) for _, r in receipts(out, store)]
    return max(seqs, default=0)


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def _ots_leg(data: bytes, ots_submit) -> tuple[dict, bytes | None]:
    """Submit the head's SHA-256. A calendar failure is recorded, never fatal:
    the Rekor leg already holds."""
    try:
        res = ots_submit(hashlib.sha256(data).digest())
    except Exception as exc:  # noqa: BLE001 -- recorded in the receipt
        return {"state": "failed", "error": f"{type(exc).__name__}: {exc}"}, None
    return {"state": "pending", "calendar": res["calendar"],
            "submitted_hex": res["submitted_hex"], "nonce_hex": res["nonce_hex"]}, res["ots"]


def anchor_store(signer: Signer, sign_ph, store: str, out: Path, *, request,
                 ots_submit=None) -> dict:
    """Anchor one store's current head. Returns a result line for the log."""
    head = signer.head({"store": store}, dict(JOB_ISOLATION))
    data = head_bytes(head)
    sha = hashlib.sha256(data).hexdigest()
    label = f"signer-head/{store_key(store)}/seq-{head['seq']}"
    entry = rekor_submit.proposed_entry(data, sign_ph, signer.public)
    uuid, logged = rekor_submit.submit(entry, request)
    rekor = rekor_submit.build_record(label, data, signer.public, uuid, logged)
    check = rekor_verify.verify_record(rekor, data, signer.public)
    if not check["ok"]:
        raise rekor_submit.RekorError(f"Rekor returned an entry that does not verify: "
                                      f"{check['reasons']}")
    ots, proof = ({"state": "off"}, None) if ots_submit is None else _ots_leg(data, ots_submit)
    path = Path(out) / store_key(store) / f"head-{head['seq']:010d}-{sha[:8]}.json"
    if proof is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.with_suffix(".ots").write_bytes(proof)
    _write(path, {"schema": RECEIPT_SCHEMA, "store_key": store_key(store),
                  "signed_head": head, "head_sha256": sha, "rekor": rekor, "ots": ots,
                  "does_not_prove": rekor_verify.does_not_prove()})
    return {"store_key": store_key(store), "seq": head["seq"], "anchored": True,
            "log_index": rekor["log_index"], "ots": ots["state"], "receipt": path.name}


def upgrade_pending(out: Path, store: str, ots_upgrade) -> int:
    """Try to upgrade every pending OpenTimestamps proof of ``store``. Returns
    how many upgraded. A calendar that has not confirmed yet is not an error."""
    done = 0
    for path, rec in receipts(out, store):
        proof_path = path.with_suffix(".ots")
        if (rec.get("ots") or {}).get("state") != "pending" or not proof_path.exists():
            continue
        digest = bytes.fromhex(rec["head_sha256"])
        try:
            upgraded = ots_upgrade(proof_path.read_bytes(), digest)
        except Exception:  # noqa: BLE001 -- keep the pending proof, retry next run
            continue
        if upgraded:
            proof_path.write_bytes(upgraded)
            rec["ots"]["state"] = "bitcoin"
            _write(path, rec)
            done += 1
    return done


def run_once(home: Path, out: Path, *, min_new: int = 1, request=None,
             ots_submit=None, ots_upgrade=None, dry_run: bool = False) -> dict:
    """One pass over every store. ``request``, ``ots_submit`` and ``ots_upgrade``
    are injected in tests; ``None`` for the OpenTimestamps legs turns them off."""
    signer = Signer(Path(home))
    request = request or rekor_submit.urllib_request
    results, failed = [], 0
    sign_ph = None
    for store in signer.journal.stores():
        seq = signer.journal.head(store)["seq"]
        last = _last_seq(out, store)
        line = {"store_key": store_key(store), "seq": seq, "last_anchored_seq": last}
        if ots_upgrade is not None:
            line["ots_upgraded"] = upgrade_pending(out, store, ots_upgrade)
        if seq == 0 or seq - last < max(1, min_new):
            results.append({**line, "anchored": False, "why": "not enough new records"})
            continue
        if dry_run:
            results.append({**line, "anchored": False, "why": "dry run"})
            continue
        if sign_ph is None:
            sign_ph, _ = rekor_submit.ph_signer_from_seed(keys.load_seed(Path(home)))
        try:
            results.append({**line, **anchor_store(signer, sign_ph, store, out,
                                                   request=request, ots_submit=ots_submit)})
        except (RuntimeError, OSError, ValueError) as exc:
            failed += 1
            results.append({**line, "anchored": False, "error": f"{type(exc).__name__}: {exc}"})
    return {"ok": failed == 0, "results": results}


def live_legs(ots: bool):
    """The real transports: Rekor over urllib, OpenTimestamps calendars."""
    if not ots:
        return rekor_submit.urllib_request, None, None
    from .. import anchor_submit
    return rekor_submit.urllib_request, anchor_submit.submit, anchor_submit.upgrade_proof
