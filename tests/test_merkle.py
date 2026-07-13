"""test_merkle.py — Merkle inclusion proofs verify, and tampering is caught.

Success criteria:
  - for every tree size 1..17 and every leaf, a generated proof verifies.
  - a wrong leaf, wrong index, or a mutated root fails verification.
  - the root is deterministic and moves when any leaf changes.
"""
import pytest

from harness.merkle import (
    inclusion_proof,
    merkle_root,
    root_hex,
    verify_inclusion,
)


def _leaves(n):
    return [f"receipt-{i}".encode() for i in range(n)]


def test_every_leaf_verifies_across_sizes():
    for n in range(1, 18):
        leaves = _leaves(n)
        root = merkle_root(leaves)
        for i in range(n):
            proof = inclusion_proof(leaves, i)
            assert verify_inclusion(leaves[i], i, n, proof, root), (n, i)


def test_tampering_is_caught():
    leaves = _leaves(8)
    root = merkle_root(leaves)
    proof = inclusion_proof(leaves, 3)
    assert verify_inclusion(leaves[3], 3, 8, proof, root)
    assert not verify_inclusion(b"forged", 3, 8, proof, root)       # wrong leaf
    assert not verify_inclusion(leaves[3], 4, 8, proof, root)       # wrong index
    assert not verify_inclusion(leaves[3], 3, 8, proof, bytes(32))  # wrong root


def test_root_is_deterministic_and_moves_on_change():
    a = merkle_root(_leaves(5))
    assert a == merkle_root(_leaves(5))                 # deterministic
    changed = _leaves(5)
    changed[2] = b"different"
    assert merkle_root(changed) != a                    # any change moves the root
    assert root_hex(_leaves(5)).startswith("sha256:")


def test_out_of_range_index_raises():
    with pytest.raises(IndexError):
        inclusion_proof(_leaves(3), 5)
