"""Tests for the author-side signer.

The verifier modules (`receipt_sign`, `tree_head`) deliberately never generate a
key: they take a signature "produced elsewhere". This is elsewhere. The contract
these tests pin: a key generated here, loaded here, produces signatures the
existing stdlib verifiers accept over the SAME preimage they recompute -- and the
generator hands back only public material, never the private half.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("cryptography")

import receipt_factories as factories                                 # noqa: E402
from harness import receipt_sign, receipt_signer, tree_head           # noqa: E402


def _make_key(tmp_path):
    return receipt_signer.generate_signing_key(
        tmp_path / "receipt-signing-ed25519", comment="test@flywheel")


def test_signed_receipt_verifies_with_the_stdlib_verifier(tmp_path):
    info = _make_key(tmp_path)
    key = receipt_signer.load_signing_key(info.private_key_path)
    signed = receipt_signer.sign_receipt(factories.receipt(), key)
    ok, reason = receipt_sign.verify_signed(signed.to_dict(), key.public_key_bytes)
    assert (ok, reason) == (True, "ok")


def test_signature_binds_the_claim_not_the_recorded_digest(tmp_path):
    info = _make_key(tmp_path)
    key = receipt_signer.load_signing_key(info.private_key_path)
    envelope = receipt_signer.sign_receipt(factories.receipt(), key).to_dict()
    # Alter the body while leaving the good signature in place. The verifier
    # recomputes claim_sha256 from the body, so this must fail closed.
    envelope["receipt"]["objective"] = "999"
    ok, reason = receipt_sign.verify_signed(envelope, key.public_key_bytes)
    assert ok is False
    assert reason == "digest_mismatch"


def test_a_different_key_is_a_named_refusal(tmp_path):
    info = _make_key(tmp_path)
    key = receipt_signer.load_signing_key(info.private_key_path)
    other = receipt_signer.load_signing_key(
        receipt_signer.generate_signing_key(
            tmp_path / "other", comment="other@flywheel").private_key_path)
    envelope = receipt_signer.sign_receipt(factories.receipt(), key).to_dict()
    ok, reason = receipt_sign.verify_signed(envelope, other.public_key_bytes)
    assert (ok, reason) == (False, "bad_signature")


def test_one_key_also_signs_a_tree_head(tmp_path):
    info = _make_key(tmp_path)
    key = receipt_signer.load_signing_key(info.private_key_path)
    head = {"size": 7, "root": "sha256:" + "a" * 64}
    signed_head = tree_head.sign_head(
        head, key.sign, public_key=key.public_key_bytes,
        timestamp="2026-08-27T00:00:00Z")
    ok, reason = tree_head.check_signed_head(signed_head, key.public_key_bytes)
    assert (ok, reason) == (True, "ok")


def test_generator_returns_only_public_material(tmp_path):
    info = _make_key(tmp_path)
    # The private key is on disk as a real OpenSSH key...
    priv = info.private_key_path.read_bytes()
    assert priv.startswith(b"-----BEGIN OPENSSH PRIVATE KEY-----")
    # ...and no field of the returned info carries it.
    for value in vars(info).values():
        assert priv not in repr(value).encode()
        assert b"PRIVATE KEY" not in repr(value).encode()
    assert len(info.public_key_bytes) == 32


def test_fingerprint_matches_openssh(tmp_path):
    info = _make_key(tmp_path)
    out = subprocess.run(
        ["ssh-keygen", "-lf", str(info.public_key_path)],
        capture_output=True, text=True, check=True).stdout
    # ssh-keygen prints "256 SHA256:<b64> comment (ED25519)"
    assert info.fingerprint in out


def test_refuses_to_overwrite_an_existing_key(tmp_path):
    _make_key(tmp_path)
    with pytest.raises(receipt_signer.SigningKeyError):
        receipt_signer.generate_signing_key(
            tmp_path / "receipt-signing-ed25519", comment="again@flywheel")
