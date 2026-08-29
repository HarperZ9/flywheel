"""The anchor CLI's testable core: keygen output, stamp, verify, and upgrade.

These exercise the pure core the CLI is built from: what `keygen` prints (public
material only, never the secret), what `stamp` writes (a head a stranger checks,
with the timestamp record embedded), what `verify` concludes, and how `upgrade`
records a Bitcoin block. The network legs are thin wrappers over `anchor_submit`,
injected here so the core runs offline; the live round trip is proven separately
against a real calendar. The cmd-level wiring is covered in
test_flywheel_anchor_cli.py, the Zenodo leg in test_flywheel_anchor_zenodo.py.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
pytest.importorskip("cryptography")

from tests._anchor_fixtures import (  # noqa: E402
    GENESIS_HEADER, GENESIS_MERKLE, HEAD, TS, _calendar_reply, _fake_submit,
    _full_block_proof, _key, fa, ots_verify, receipt_signer)


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


def test_apply_upgrade_confirms_and_stores_the_verified_block_header():
    # a spliced full proof whose merkle root is the artifact digest, with the
    # matching header, is confirmed AND carries the header a stranger needs to
    # prove the block offline. (digest == genesis merkle so a real header exists.)
    digest = GENESIS_MERKLE
    rec = {"digest_hex": digest.hex(),
           "ots": {"state": "pending", "submitted_hex": "de",
                   "nonce_hex": "ad", "calendar": "https://cal.example"}}
    new_rec, new_ots = fa.apply_upgrade(rec, _full_block_proof(digest),
                                        header=GENESIS_HEADER)
    assert new_rec["ots"]["state"] == "confirmed"
    assert new_rec["ots"]["block_height"] == 0
    assert new_rec["ots"]["block_header"] == GENESIS_HEADER.hex()
    # the record now verifies offline from its own stored header, no network
    checked = ots_verify.verify(new_ots, digest, fa._header_provider(new_rec))
    assert checked["ok"] is True


def test_apply_upgrade_stores_no_header_when_the_block_does_not_verify():
    # a bitcoin leaf landed, but the supplied header does not verify the block:
    # the height is recorded honestly, the wrong header is NOT persisted.
    digest = GENESIS_MERKLE
    rec = {"digest_hex": digest.hex(), "ots": {"state": "pending"}}
    wrong = bytes(80)   # 80 zero bytes: no work, wrong merkle
    new_rec, _ = fa.apply_upgrade(rec, _full_block_proof(digest), header=wrong)
    assert new_rec["ots"]["state"] == "confirmed"     # the block did land
    assert new_rec["ots"]["block_height"] == 0
    assert "block_header" not in new_rec["ots"]        # but never a header that lies


def test_apply_upgrade_stays_pending_without_a_bitcoin_leaf():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=_fake_submit())
    digest = bytes.fromhex(anchor_rec["digest_hex"])
    # the calendar's continuation is still just a pending promise, no block
    pending_full = fa.anchor_submit.build_ots(
        digest, bytes.fromhex(anchor_rec["ots"]["nonce_hex"]), _calendar_reply())
    new_anchor, _ = fa.apply_upgrade(anchor_rec, pending_full)
    assert new_anchor["ots"]["state"] == "pending"
    assert "block_header" not in new_anchor["ots"]


def test_header_provider_yields_the_stored_header_for_its_height_only():
    rec = {"ots": {"block_header": GENESIS_HEADER.hex(), "block_height": 964462}}
    provider = fa._header_provider(rec)
    assert provider(964462) == GENESIS_HEADER
    assert provider(964463) is None            # a different height gets nothing


def test_header_provider_is_none_without_a_stored_header():
    assert fa._header_provider({"ots": {"state": "pending"}}) is None
    assert fa._header_provider({}) is None


def test_a_stamped_anchor_serializes_to_json_without_raw_bytes():
    key = _key()
    anchor_rec, _ = fa.build_stamp(HEAD, key, TS, submit=_fake_submit())
    round_tripped = json.loads(json.dumps(anchor_rec))
    assert round_tripped["ots"]["submitted_hex"] == anchor_rec["ots"]["submitted_hex"]
