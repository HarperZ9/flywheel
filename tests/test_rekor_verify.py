"""The stdlib Rekor verifier: Ed25519ph, P-256, Merkle proofs, and the record check.

Every positive check here has a negative twin: a verifier that accepts the real
record but also accepts a tampered one would be checking nothing.
"""
from __future__ import annotations

import hashlib

import pytest

from harness import ed25519_verify, ed25519ph_verify, p256_verify, rekor_online, rekor_verify


# --- Ed25519ph -----------------------------------------------------------------

# RFC 8032 section 7.3, test vector "abc" for Ed25519ph.
RFC_PH_PUBLIC = bytes.fromhex("ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf")
RFC_PH_SIG = bytes.fromhex(
    "98a70222f0b8121aa9d30f813d683f809e462b469c7ff87639499bb94e6dae41"
    "31f85042463c2a355a2003d062adf5aaa10b8c61e636062aaad11c2a26083406")


def test_ed25519ph_rfc8032_vector():
    assert ed25519ph_verify.verify_ph(RFC_PH_PUBLIC, b"abc", RFC_PH_SIG)
    assert not ed25519ph_verify.verify_ph(RFC_PH_PUBLIC, b"abd", RFC_PH_SIG)


def test_ph_and_pure_signatures_never_cross_verify():
    # The same signature must not verify under the other scheme.
    assert not ed25519_verify.verify(RFC_PH_PUBLIC, b"abc", RFC_PH_SIG)


def test_ph_matches_libsodium_signer():
    nacl = pytest.importorskip("nacl.bindings")
    public, secret = nacl.crypto_sign_seed_keypair(bytes(range(32)))
    state = nacl.crypto_sign_ed25519ph_state()
    nacl.crypto_sign_ed25519ph_update(state, b"flywheel")
    sig = nacl.crypto_sign_ed25519ph_final_create(state, secret)
    assert ed25519ph_verify.verify_ph(public, b"flywheel", sig)
    assert not ed25519ph_verify.verify_ph(public, b"flywheeL", sig)


# --- P-256 -----------------------------------------------------------------------

def test_p256_rejects_off_curve_and_noncanonical_der():
    der = p256_verify.pem_to_der(rekor_verify.REKOR_PUBLIC_KEY_PEM)
    p256_verify.public_key_from_spki(der)
    with pytest.raises(p256_verify.P256Error):
        p256_verify.public_key_from_spki(der[:-1] + bytes([der[-1] ^ 1]))
    with pytest.raises(p256_verify.P256Error):
        p256_verify.decode_der_signature(bytes.fromhex("3006020100020101") + b"\x00")
    with pytest.raises(p256_verify.P256Error):
        p256_verify.decode_der_signature(bytes.fromhex("300702020001020101"))


def test_pinned_log_id_is_the_hash_of_the_pinned_key():
    assert rekor_verify.pinned_log_id() == rekor_verify.REKOR_LOG_ID


# --- Merkle proofs -----------------------------------------------------------------

def _mth(leaves: list[bytes]) -> bytes:
    if len(leaves) == 1:
        return rekor_verify.leaf_hash(leaves[0])
    k = 1
    while k * 2 < len(leaves):
        k *= 2
    return hashlib.sha256(b"\x01" + _mth(leaves[:k]) + _mth(leaves[k:])).digest()


def _path(m: int, leaves: list[bytes]) -> list[bytes]:
    if len(leaves) == 1:
        return []
    k = 1
    while k * 2 < len(leaves):
        k *= 2
    if m < k:
        return _path(m, leaves[:k]) + [_mth(leaves[k:])]
    return _path(m - k, leaves[k:]) + [_mth(leaves[:k])]


def _subproof(m: int, leaves: list[bytes], whole: bool) -> list[bytes]:
    n = len(leaves)
    if m == n:
        return [] if whole else [_mth(leaves)]
    k = 1
    while k * 2 < n:
        k *= 2
    if m <= k:
        return _subproof(m, leaves[:k], whole) + [_mth(leaves[k:])]
    return _subproof(m - k, leaves[k:], False) + [_mth(leaves[:k])]


LEAVES = [bytes([i]) * 3 for i in range(17)]


def test_inclusion_every_leaf_every_size():
    for n in range(1, len(LEAVES) + 1):
        tree = LEAVES[:n]
        root = _mth(tree)
        for i in range(n):
            got = rekor_verify.root_from_inclusion(i, n, rekor_verify.leaf_hash(tree[i]), _path(i, tree))
            assert got == root
        bad = rekor_verify.root_from_inclusion(0, n, rekor_verify.leaf_hash(b"zz"), _path(0, tree))
        assert bad != root


def test_consistency_every_pair():
    for n in range(1, len(LEAVES) + 1):
        for m in range(1, n + 1):
            proof = _subproof(m, LEAVES[:n], True)
            r1, r2 = _mth(LEAVES[:m]), _mth(LEAVES[:n])
            assert rekor_online.verify_consistency(m, n, proof, r1, r2), (m, n)
            if m < n:
                assert not rekor_online.verify_consistency(m, n, proof, r2, r2)
