"""The receipt transparency log: a Merkle tree over envelope hashes, so
a third party can verify one receipt's inclusion without holding the
whole ledger. The root moves if any leaf moves; an inclusion proof binds
one leaf to the root through named siblings; a wrong leaf or wrong root
fails. Standard transparency-log semantics, zero dependencies."""

import hashlib

import pytest

from harness.transparency_log import (inclusion_proof, merkle_root,
                                      verify_inclusion)

LEAVES = [hashlib.sha256(f"envelope-{i}".encode()).hexdigest()
          for i in range(7)]


def test_root_is_deterministic_and_leaf_sensitive():
    r1 = merkle_root(LEAVES)
    r2 = merkle_root(list(LEAVES))
    assert r1 == r2 and len(r1) == 64
    tampered = list(LEAVES)
    tampered[3] = hashlib.sha256(b"tampered").hexdigest()
    assert merkle_root(tampered) != r1


def test_every_leaf_proves_inclusion():
    root = merkle_root(LEAVES)
    for i, leaf in enumerate(LEAVES):
        proof = inclusion_proof(LEAVES, i)
        assert verify_inclusion(leaf, proof, root) is True


def test_wrong_leaf_and_wrong_root_both_fail():
    root = merkle_root(LEAVES)
    proof = inclusion_proof(LEAVES, 2)
    wrong_leaf = hashlib.sha256(b"not-in-log").hexdigest()
    assert verify_inclusion(wrong_leaf, proof, root) is False
    assert verify_inclusion(LEAVES[2], proof, "0" * 64) is False


def test_single_leaf_and_empty_log():
    one = [LEAVES[0]]
    assert merkle_root(one) != LEAVES[0], "a root is a commitment, not a copy"
    assert verify_inclusion(LEAVES[0], inclusion_proof(one, 0),
                            merkle_root(one)) is True
    with pytest.raises(ValueError):
        merkle_root([])


def test_appending_preserves_old_inclusions_under_the_new_root():
    grown = LEAVES + [hashlib.sha256(b"envelope-7").hexdigest()]
    new_root = merkle_root(grown)
    proof = inclusion_proof(grown, 3)
    assert verify_inclusion(LEAVES[3], proof, new_root) is True
