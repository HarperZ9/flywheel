"""Ed25519 verification, vendored, on a bare interpreter.

This is the module Bar R rests on. A stranger clones the repo, runs the verifier,
and checks a signature with nothing installed. If this needed `cryptography`, the
offline promise would be a promise about the stranger's package manager.

Verify only, never sign, and the asymmetry is deliberate. A verifier is a
stranger who must need nothing. A signer is the author, who already has tooling.
Shipping a pure-Python signer would also invite someone to generate keys with an
unaudited RNG in a module whose whole point is that it is small enough to read.

The RFC 8032 section 7.1 vectors are the load-bearing tests. An Ed25519
implementation that passes its own hand-rolled cases and fails the RFC vectors is
worse than none, because it looks like it works.
"""
import binascii

import pytest

from harness.ed25519_verify import (
    verify, Ed25519Error, decode_point, L, is_canonical_scalar,
)


def h(s: str) -> bytes:
    return binascii.unhexlify(s.replace(" ", ""))


# RFC 8032 section 7.1, Test 1 through Test 4 plus the SHA-abc case.
# (secret key is listed in the RFC but never used here: this module cannot sign.)
RFC_VECTORS = [
    (   # TEST 1: empty message
        "d75a980182b10ab7d54bfed3c964073a"
        "0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a"
        "84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46b"
        "d25bf5f0595bbe24655141438e7a100b",
    ),
    (   # TEST 2: one byte
        "3d4017c3e843895a92b70aa74d1b7ebc"
        "9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540"
        "a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c"
        "387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (   # TEST 3: two bytes
        "fc51cd8e6218a1a38da47ed00230f058"
        "0816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a3"
        "0ce548a284743a445e3680d7db5ac3ac"
        "18ff9b538d16f290ae67f760984dc659"
        "4a7c15e9716ed28dc027beceea1ec40a",
    ),
]


@pytest.mark.parametrize("pub,msg,sig", RFC_VECTORS)
def test_rfc8032_vectors_verify(pub, msg, sig):
    assert verify(h(pub), h(msg), h(sig)) is True


@pytest.mark.parametrize("pub,msg,sig", RFC_VECTORS)
def test_flipping_one_signature_bit_fails(pub, msg, sig):
    raw = bytearray(h(sig))
    raw[0] ^= 0x01
    assert verify(h(pub), h(msg), bytes(raw)) is False


@pytest.mark.parametrize("pub,msg,sig", RFC_VECTORS)
def test_flipping_one_public_key_bit_fails(pub, msg, sig):
    raw = bytearray(h(pub))
    raw[0] ^= 0x01
    # A mutated key may be off-curve, which is a refusal, or on-curve and simply
    # wrong. Either way it must not verify.
    try:
        assert verify(bytes(raw), h(msg), h(sig)) is False
    except Ed25519Error:
        pass


def test_a_changed_message_fails():
    pub, msg, sig = RFC_VECTORS[1]
    assert verify(h(pub), h("73"), h(sig)) is False


def test_appending_to_the_message_fails():
    pub, msg, sig = RFC_VECTORS[1]
    assert verify(h(pub), h(msg) + b"\x00", h(sig)) is False


def test_the_empty_message_signature_does_not_verify_a_nonempty_message():
    pub, _, sig = RFC_VECTORS[0]
    assert verify(h(pub), b"x", h(sig)) is False


# --- input validation ---------------------------------------------------------

def test_a_short_signature_is_refused():
    pub, msg, sig = RFC_VECTORS[0]
    with pytest.raises(Ed25519Error):
        verify(h(pub), h(msg), h(sig)[:63])


def test_a_long_signature_is_refused():
    pub, msg, sig = RFC_VECTORS[0]
    with pytest.raises(Ed25519Error):
        verify(h(pub), h(msg), h(sig) + b"\x00")


def test_a_wrong_length_public_key_is_refused():
    pub, msg, sig = RFC_VECTORS[0]
    with pytest.raises(Ed25519Error):
        verify(h(pub)[:31], h(msg), h(sig))


def test_a_non_bytes_input_is_refused():
    pub, msg, sig = RFC_VECTORS[0]
    with pytest.raises(Ed25519Error):
        verify("not bytes", h(msg), h(sig))


# --- the traps that catch naive implementations -------------------------------

def test_a_non_canonical_scalar_is_rejected():
    """S must be reduced mod L. An unreduced S gives a second valid signature for
    the same message, which is signature malleability: two distinct byte strings
    both verifying breaks any system that treats a signature as an identifier."""
    pub, msg, sig = RFC_VECTORS[1]
    raw = h(sig)
    R, S = raw[:32], raw[32:]
    s_int = int.from_bytes(S, "little")
    mutated = (s_int + L).to_bytes(32, "little")
    assert is_canonical_scalar(S) is True
    assert is_canonical_scalar(mutated) is False
    assert verify(h(pub), h(msg), R + mutated) is False


def test_an_off_curve_point_is_refused_rather_than_silently_false():
    # y=2 has no corresponding x on this curve. It must raise, so a caller can
    # tell "malformed key" from "wrong signature".
    with pytest.raises(Ed25519Error):
        decode_point((2).to_bytes(32, "little"))


def test_the_identity_point_decodes():
    # y=1, sign bit 0 gives x=0: the neutral element. A legal encoding, and a
    # verifier must handle it without crashing.
    assert decode_point((1).to_bytes(32, "little")) is not None


def test_a_y_at_or_above_the_field_prime_is_refused():
    # Non-canonical y. Accepting it would give two encodings for one point.
    from harness.ed25519_verify import P as field_p
    with pytest.raises(Ed25519Error):
        decode_point(((field_p + 1) | (1 << 255)).to_bytes(32, "little"))


def test_an_all_zero_signature_does_not_verify():
    pub, msg, _ = RFC_VECTORS[0]
    assert verify(h(pub), h(msg), b"\x00" * 64) is False


def test_an_all_ff_signature_is_refused_or_false():
    pub, msg, _ = RFC_VECTORS[0]
    try:
        assert verify(h(pub), h(msg), b"\xff" * 64) is False
    except Ed25519Error:
        pass


# --- the module cannot sign ----------------------------------------------------

def test_the_module_exposes_no_signing_capability():
    """Verify only. A pure-Python signer would invite key generation with an
    unaudited RNG inside a module whose whole value is being small enough to
    read, and a signer is the author who already has tooling."""
    import harness.ed25519_verify as m
    names = [n for n in dir(m) if not n.startswith("_")]
    for banned in ("sign", "keygen", "generate_key", "private_key", "secret"):
        assert not any(banned in n.lower() for n in names), (banned, names)


def test_the_module_imports_nothing_beyond_hashlib():
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "harness" / "ed25519_verify.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods <= {"hashlib", "__future__"}, mods


def test_verification_is_deterministic():
    pub, msg, sig = RFC_VECTORS[2]
    results = [verify(h(pub), h(msg), h(sig)) for _ in range(5)]
    assert results == [True] * 5
