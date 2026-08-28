"""The anchor CLI ties the key, the signed head, and the timestamp end to end.

These exercise the testable core the CLI is built from: what `keygen` prints
(public material only, never the secret), what `stamp` writes (a head a stranger
checks, with the timestamp record embedded), what `verify` concludes, and how
`upgrade` rebuilds a full proof from the artifact digest. The network legs are
thin wrappers over `anchor_submit`, injected here so the core is exercised
offline; the live round trip is proven separately against a real calendar.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import ots_verify  # noqa: E402
from harness import receipt_signer  # noqa: E402
from scripts import flywheel_anchor as fa  # noqa: E402

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey)

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")
HEAD = {"schema": "flywheel.tree-head/v1", "size": 7, "root": "sha256:" + "a" * 64}
TS = "2026-08-27T00:00:00Z"


def _key():
    return receipt_signer.SigningKey(Ed25519PrivateKey.generate())


def _varuint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _calendar_reply(uri="https://cal.example/x"):
    """A calendar's serialized reply: from the SUBMITTED digest to a pending leaf."""
    payload = _varuint(len(uri.encode())) + uri.encode()
    return b"\x00" + PENDING_TAG + _varuint(len(payload)) + payload


def _fake_submit(reply=None):
    """A submit() stand-in: nonces the digest, wraps a canned calendar reply."""
    reply = _calendar_reply() if reply is None else reply

    def submit(raw_digest):
        nonce = b"\x5a" * 16
        ots = fa.anchor_submit.build_ots(raw_digest, nonce, reply)
        submitted = fa.anchor_submit.submitted_digest(raw_digest, nonce)
        return {"ots": ots, "submitted_hex": submitted.hex(),
                "nonce_hex": nonce.hex(), "calendar": "https://cal.example",
                "errors": []}
    return submit


def test_keygen_report_shows_public_material_and_never_the_private_key():
    info = receipt_signer.SigningKeyInfo(
        private_key_path=Path("/held/offline/receipt-signing-ed25519"),
        public_key_path=Path("/held/offline/receipt-signing-ed25519.pub"),
        public_key_bytes=b"\x11" * 32,
        key_id=receipt_signer.key_id_for(b"\x11" * 32),
        fingerprint=receipt_signer.fingerprint_for(b"\x11" * 32))
    out = "\n".join(fa.keygen_report(info))
    assert info.key_id in out and info.fingerprint in out
    assert "ssh-ed25519 " in out            # the public line to upload
    assert "gh ssh-key add" in out          # the exact next command
    assert "BEGIN OPENSSH PRIVATE KEY" not in out
    assert "\x11" * 32 not in out           # no raw secret, ever


def test_build_stamp_offline_produces_a_head_a_stranger_can_check():
    key = _key()
    anchor_rec, ots = fa.build_stamp(HEAD, key, TS, submit=None)
    assert ots is None
    assert anchor_rec["ots"]["state"] == "absent"
    r = fa.verify_stamp(anchor_rec, None, key.public_key_bytes)
    assert r["head_ok"] is True


def test_build_stamp_online_embeds_the_ots_record_and_binds_the_digest():
    key = _key()
    anchor_rec, ots = fa.build_stamp(HEAD, key, TS, submit=_fake_submit())
    assert ots is not None
    assert anchor_rec["ots"]["state"] == "pending"
    assert anchor_rec["ots"]["calendar"] == "https://cal.example"
    assert len(bytes.fromhex(anchor_rec["ots"]["nonce_hex"])) == 16
    r = fa.verify_stamp(anchor_rec, ots, key.public_key_bytes)
    assert r["timestamp"]["file_digest"] == anchor_rec["digest_hex"]


def test_verify_stamp_catches_a_timestamp_over_a_different_digest():
    key = _key()
    # a calendar reply that (via the fake) commits the wrong artifact: forge by
    # stamping a different digest, then checking against the real anchor.
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    wrong = fa.anchor_submit.build_ots(b"\x00" * 32, b"\x5a" * 16, _calendar_reply())
    r = fa.verify_stamp(anchor_rec, wrong, key.public_key_bytes)
    assert r["ok"] is False
    assert "digest_mismatch" in r["timestamp"]["reason"]


def test_apply_upgrade_rebuilds_a_full_proof_from_the_artifact_digest():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=_fake_submit())
    digest = bytes.fromhex(anchor_rec["digest_hex"])
    nonce = bytes.fromhex(anchor_rec["ots"]["nonce_hex"])
    # the calendar's upgraded reply (still pending here: a real block needs a
    # real block, which is the point of the anchor)
    new_anchor, new_ots = fa.apply_upgrade(anchor_rec, digest, nonce, _calendar_reply())
    checked = ots_verify.verify(new_ots, digest)
    assert checked["file_digest"] == digest.hex()
    assert new_anchor["ots"]["state"] == "pending"   # no bitcoin leaf yet


def test_a_stamped_anchor_serializes_to_json_without_raw_bytes():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=_fake_submit())
    round_tripped = json.loads(json.dumps(anchor_rec))
    assert round_tripped["ots"]["submitted_hex"] == anchor_rec["ots"]["submitted_hex"]


# --- the Zenodo durability leg: a dry run before the one live mint ----------
#
# The DOI is irreversible: a published record cannot be unpublished. So the
# producer step before it is a dry run that computes the exact (filename, size,
# bound digest) a deposit WOULD carry and a metadata skeleton to review, and
# calls nothing. It must also refuse a record whose stored digest disagrees with
# its own head here, at the terminal, not at the network, so a corrupt record is
# caught before the operator crosses the live gate.

def test_zenodo_dry_run_reports_the_bound_bytes_and_the_digest():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    report = fa.zenodo_dry_run(anchor_rec)
    assert report["filename"] == "signed-head.json"
    # the deposited bytes are the canonical signed head, and their sha256 IS the
    # record's digest, so the DOI witnesses the same digest the Bitcoin leg does
    from harness.receipt_fields import canonical
    assert report["size_bytes"] == len(canonical(anchor_rec["signed_head"]).encode())
    assert report["bound_digest"] == anchor_rec["anchor_digest"]
    assert report["digest_hex"] == anchor_rec["digest_hex"]
    assert report["metadata"]["metadata"]["title"]        # a fillable skeleton
    assert report["metadata"]["metadata"]["creators"]


def test_zenodo_dry_run_refuses_a_record_whose_digest_disagrees_with_its_head():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    anchor_rec["digest_hex"] = "00" * 32          # no longer matches the head
    with pytest.raises(fa.zenodo_deposit.DepositError):
        fa.zenodo_dry_run(anchor_rec)


def test_zenodo_dry_run_surfaces_the_binding_caveats():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    report = fa.zenodo_dry_run(anchor_rec)
    joined = " ".join(report["does_not_prove"])
    assert "NOT_PROVES_THE_TIMESTAMP" in joined     # a DOI alone orders nothing


def test_zenodo_dry_run_metadata_is_overridable():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    report = fa.zenodo_dry_run(
        anchor_rec, title="Custom title",
        creators=[{"name": "Doe, Jane"}])
    md = report["metadata"]["metadata"]
    assert md["title"] == "Custom title"
    assert md["creators"] == [{"name": "Doe, Jane"}]


def test_cmd_zenodo_is_a_dry_run_and_never_touches_the_network(tmp_path, capsys,
                                                               monkeypatch):
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    path = tmp_path / "anchor.json"
    path.write_text(json.dumps(anchor_rec), encoding="utf-8")

    def _boom(*a, **k):
        raise AssertionError("a dry run must not reach the deposit client")

    monkeypatch.setattr(fa.zenodo_deposit, "deposit", _boom)
    code = fa.main(["zenodo", "--anchor", str(path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "signed-head.json" in out
    assert anchor_rec["anchor_digest"] in out
    assert "dry run" in out.lower()          # says plainly it minted nothing


def test_cmd_zenodo_refuses_a_corrupt_record_with_a_nonzero_exit(tmp_path, capsys):
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=None)
    anchor_rec["digest_hex"] = "00" * 32
    path = tmp_path / "anchor.json"
    path.write_text(json.dumps(anchor_rec), encoding="utf-8")
    code = fa.main(["zenodo", "--anchor", str(path)])
    assert code != 0
    err = capsys.readouterr().err
    assert "REFUSED" in err
