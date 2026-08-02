"""Tests for ed25519 asymmetric signatures and signed-receipt wrapper."""
from __future__ import annotations

import pytest

from harness.crypto.signatures import (
    SIGNED_SCHEMA,
    backend_name,
    crypto_available,
    generate_keypair,
    public_key_fingerprint,
    sign_receipt,
    verify_signed,
    verify_signature,
    wrap_signed,
)


# --- backend detection --------------------------------------------------


def test_crypto_available():
    """Crypto should be available (cryptography or pynacl installed)."""
    assert crypto_available() is True
    assert backend_name() in ("cryptography", "pynacl")


# --- keypair generation -------------------------------------------------


def test_generate_keypair():
    priv, pub = generate_keypair()
    assert len(priv) > 100  # PEM or base64
    assert len(pub) > 30


def test_keypair_unique():
    priv1, pub1 = generate_keypair()
    priv2, pub2 = generate_keypair()
    assert pub1 != pub2


def test_public_key_fingerprint():
    _, pub = generate_keypair()
    fp = public_key_fingerprint(pub)
    assert fp.startswith("sha256:")
    assert len(fp) == 7 + 16  # "sha256:" + 16 hex chars


# --- sign and verify ----------------------------------------------------


def test_sign_and_verify_match():
    priv, pub = generate_keypair()
    receipt = {"schema": "test", "data": "hello"}
    sig = sign_receipt(receipt, priv)
    assert verify_signature(receipt, sig, pub) is True


def test_verify_rejects_tampered_receipt():
    priv, pub = generate_keypair()
    receipt = {"schema": "test", "data": "original"}
    sig = sign_receipt(receipt, priv)
    receipt["data"] = "tampered"
    assert verify_signature(receipt, sig, pub) is False


def test_verify_rejects_wrong_key():
    priv1, _ = generate_keypair()
    _, pub2 = generate_keypair()
    receipt = {"schema": "test", "data": "hello"}
    sig = sign_receipt(receipt, priv1)
    assert verify_signature(receipt, sig, pub2) is False


def test_sign_receipt_deterministic():
    """ed25519 is deterministic: same key + same message = same signature."""
    priv, pub = generate_keypair()
    receipt = {"schema": "test", "data": "hello"}
    sig1 = sign_receipt(receipt, priv)
    sig2 = sign_receipt(receipt, priv)
    assert sig1 == sig2


# --- signed receipt wrapper --------------------------------------------


def test_wrap_signed_structure():
    priv, _ = generate_keypair()
    inner = {"schema": "flywheel.lesson/v1", "claim": "test"}
    signed = wrap_signed(inner, priv)
    assert signed["schema"] == SIGNED_SCHEMA
    assert signed["inner_receipt"] == inner
    assert signed["signature"]["algorithm"] == "ed25519"
    assert "value" in signed["signature"]
    assert "public_key" in signed["signature"]
    assert "public_key_fingerprint" in signed["signature"]


def test_verify_signed_match():
    priv, _ = generate_keypair()
    inner = {"schema": "flywheel.lesson/v1", "claim": "test lesson"}
    signed = wrap_signed(inner, priv)
    result = verify_signed(signed)
    assert result["verdict"] == "MATCH"
    assert "fingerprint" in result


def test_verify_signed_tampered_inner():
    priv, _ = generate_keypair()
    inner = {"schema": "test", "data": "original"}
    signed = wrap_signed(inner, priv)
    signed["inner_receipt"]["data"] = "tampered"
    result = verify_signed(signed)
    assert result["verdict"] == "TAMPERED"


def test_verify_signed_bad_schema():
    result = verify_signed({"schema": "wrong"})
    assert result["verdict"] == "UNVERIFIABLE"


def test_verify_signed_missing_signature():
    result = verify_signed({
        "schema": SIGNED_SCHEMA,
        "inner_receipt": {"x": 1},
    })
    assert result["verdict"] == "UNVERIFIABLE"


# --- cross-receipt compatibility ---------------------------------------


def test_wrap_any_receipt_type():
    """The wrapper works with any receipt schema."""
    priv, _ = generate_keypair()

    # Tool-call receipt
    tc = {"schema": "flywheel.tool-call-receipt/v1", "tool": "read_file"}
    signed_tc = wrap_signed(tc, priv)
    assert verify_signed(signed_tc)["verdict"] == "MATCH"

    # Lesson receipt
    lesson = {"schema": "flywheel.lesson/v1", "claim": "drift detected"}
    signed_lesson = wrap_signed(lesson, priv)
    assert verify_signed(signed_lesson)["verdict"] == "MATCH"

    # TADR classification receipt
    tadr = {"schema": "flywheel.tadr-classification/v1", "tier": "T2"}
    signed_tadr = wrap_signed(tadr, priv)
    assert verify_signed(signed_tadr)["verdict"] == "MATCH"
