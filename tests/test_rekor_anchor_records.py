"""The real Rekor anchors in the repository verify offline, and tampering is caught.

Stdlib only and no network: this runs in the dependency-free slice. The Rekor key
and log ID are pinned in `harness.rekor_verify`; the anchoring public key is
pinned here, from project-docs/records/2026-08-27-signing-key-provenance.md, and
never read from the record under test.
"""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

from harness import rekor_verify
from harness.anchor_cli import artifact_bytes, record_path, rekor_suffix

REPO = Path(__file__).resolve().parent.parent
# The prereg log's own key (artifacts/prereg/FREEZE.json) and the receipt-signing
# key (project-docs/records/2026-08-27-signing-key-provenance.md). head-0008 was
# logged once under each.
LOG_KEY = bytes.fromhex("1f85627e7e0dd4c6c73593d785b669b2abe4701ea780e26d1024b45dc1546111")
RECEIPT_KEY = bytes.fromhex("f3701ca549bb7042c569f7b22a92cddb59ccf288c5fc57a481332acad53b49c2")
ANCHOR_KEY = LOG_KEY
ANCHOR_DIR = REPO / "artifacts" / "anchor"
HEAD_0008 = REPO / "artifacts" / "prereg" / "heads" / "head-0008.json"
ANCHORED = [(HEAD_0008, LOG_KEY), (HEAD_0008, RECEIPT_KEY)]


def _load(artifact: Path, key: bytes = LOG_KEY):
    data, _ = artifact_bytes(artifact)
    rec = json.loads(record_path(artifact, ANCHOR_DIR, rekor_suffix(key))
                     .read_text(encoding="utf-8"))
    return data, rec


def test_every_anchored_head_verifies_offline_under_the_pins():
    for artifact, key in ANCHORED:
        data, rec = _load(artifact, key)
        res = rekor_verify.verify_record(rec, data, key)
        assert rec["public_key"] == key.hex()
        assert res["ok"], (artifact.name, res["reasons"])
        assert res["log_index"] == rec["log_index"]
        assert rec["search_url"].endswith(f"logIndex={rec['log_index']}")


def test_the_rekor_and_opentimestamps_anchors_witness_the_same_bytes():
    data, rec = _load(HEAD_0008)
    ots = json.loads((REPO / "artifacts" / "anchor" / "head-0008-anchor.json")
                     .read_text(encoding="utf-8"))
    assert rec["artifact"]["sha256"] == ots["digest_hex"]
    # signed-head.json is the current head and carries the same bytes.
    assert artifact_bytes(REPO / "artifacts" / "prereg" / "signed-head.json")[0] == data


def test_tampering_is_caught_at_each_layer():
    data, rec = _load(HEAD_0008)
    entry = rec["entry"]

    def reasons(mutate, artifact=data, key=ANCHOR_KEY):
        r = copy.deepcopy(rec)
        mutate(r["entry"])
        return rekor_verify.verify_record(r, artifact, key)["reasons"]

    assert "ARTIFACT_HASH_DIFFERS" in reasons(lambda e: None, artifact=data[:-1] + b" ")
    assert "BODY_KEY_NOT_PINNED_KEY" in reasons(lambda e: None, key=b"\x02" * 32)
    assert "SET_INVALID" in reasons(lambda e: e.update(integratedTime=e["integratedTime"] - 86400))
    assert "LOG_ID_NOT_PINNED" in reasons(lambda e: e.update(logID="00" * 32))

    def bad_path(e):
        h = e["verification"]["inclusionProof"]["hashes"]
        h[0] = ("0" if h[0][0] != "0" else "1") + h[0][1:]
    assert "INCLUSION_PROOF_INVALID" in reasons(bad_path)

    def bad_checkpoint(e):
        lines = e["verification"]["inclusionProof"]["checkpoint"].split("\n")
        lines[1] = str(int(lines[1]) + 1)
        e["verification"]["inclusionProof"]["checkpoint"] = "\n".join(lines)
    got = reasons(bad_checkpoint)
    assert "CHECKPOINT_DISAGREES_WITH_PROOF" in got
    assert "CHECKPOINT_SIGNATURE_INVALID" in got

    body = json.loads(base64.b64decode(entry["body"]))
    body["spec"]["data"]["hash"]["value"] = "0" * 128
    swapped = base64.b64encode(json.dumps(body).encode()).decode()
    got = reasons(lambda e: e.update(body=swapped))
    assert "ARTIFACT_HASH_DIFFERS" in got and "SET_INVALID" in got


def test_record_holds_the_fields_a_stranger_needs():
    _, rec = _load(HEAD_0008)
    assert rec["schema"] == rekor_verify.SCHEMA
    assert rec["rekor"]["log_id"] == rekor_verify.REKOR_LOG_ID
    proof = rec["entry"]["verification"]["inclusionProof"]
    assert {"checkpoint", "hashes", "logIndex", "rootHash", "treeSize"} <= set(proof)
    assert rec["entry"]["verification"]["signedEntryTimestamp"]
    assert not rec["artifact"]["path"].startswith(("/", "C:", "c:"))


def test_a_record_does_not_verify_under_the_other_key():
    data, rec = _load(HEAD_0008, LOG_KEY)
    res = rekor_verify.verify_record(rec, data, RECEIPT_KEY)
    assert not res["ok"] and "BODY_KEY_NOT_PINNED_KEY" in res["reasons"]


def test_one_key_covers_the_head_signature_and_both_anchors():
    from harness import anchor, tree_head
    data, _ = _load(HEAD_0008, LOG_KEY)
    head = json.loads(data)
    assert tree_head.check_signed_head(head, LOG_KEY) == (True, "ok")
    ots = json.loads((ANCHOR_DIR / "head-0008-anchor.json").read_text(encoding="utf-8"))
    ots_bytes = (ANCHOR_DIR / "head-0008-anchor.json.ots").read_bytes()
    res = anchor.verify_anchor(ots, LOG_KEY, ots_bytes=ots_bytes,
                               header_provider=anchor.stored_header_provider(ots))
    assert res["ok"], res
