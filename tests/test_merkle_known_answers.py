"""Known-answer tests for harness/merkle.py.

The existing test_merkle.py is entirely self-consistency: proofs produced by this
implementation verify against roots produced by this implementation. That kind of
suite passes perfectly for a tree that is internally coherent and wrong, which is
the same failure class as an elliptic curve base point recovered with the wrong
root.

So this file computes the expected roots INDEPENDENTLY, by hand, from the RFC 6962
definitions, and asserts the exact bytes. Two things get pinned:

  - domain separation: leaves are sha256(0x00 || data), interior nodes are
    sha256(0x01 || left || right). Without it an interior node can be presented as
    a leaf, which is a second-preimage attack.
  - the split rule: the recursive split is at the largest power of two STRICTLY
    below n. For n=3 that is 2|1, not 1|2. Getting this wrong yields a tree that
    disagrees with every other RFC 6962 implementation while agreeing with itself.
"""
import hashlib

import pytest

from harness.merkle import (
    leaf_hash, inclusion_proof, merkle_root, root_hex, verify_inclusion,
)


def L(data: bytes) -> bytes:
    """Leaf hash, computed here rather than imported, so the test is independent."""
    return hashlib.sha256(b"\x00" + data).digest()


def N(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


# --- domain separation, pinned to exact bytes ---------------------------------

def test_leaf_hash_uses_the_0x00_prefix():
    assert leaf_hash(b"x") == hashlib.sha256(b"\x00x").digest()


def test_a_leaf_and_a_node_of_the_same_bytes_differ():
    a, b = L(b"a"), L(b"b")
    assert leaf_hash(a + b) != N(a, b)


def test_an_interior_node_is_not_a_valid_leaf_hash_of_itself():
    interior = N(L(b"a"), L(b"b"))
    assert leaf_hash(interior) != interior


def test_the_empty_tree_root_is_sha256_of_nothing():
    assert merkle_root([]) == hashlib.sha256(b"").digest()


def test_a_one_leaf_root_is_the_leaf_hash_with_no_node_prefix():
    # A tree of one must NOT wrap its leaf in an interior node.
    assert merkle_root([b"only"]) == L(b"only")


# --- the split rule, pinned by hand -------------------------------------------

def test_two_leaf_root():
    assert merkle_root([b"a", b"b"]) == N(L(b"a"), L(b"b"))


def test_three_leaf_root_splits_two_then_one():
    expected = N(N(L(b"a"), L(b"b")), L(b"c"))
    assert merkle_root([b"a", b"b", b"c"]) == expected


def test_three_leaf_root_is_NOT_the_one_then_two_split():
    wrong = N(L(b"a"), N(L(b"b"), L(b"c")))
    assert merkle_root([b"a", b"b", b"c"]) != wrong


def test_four_leaf_root_is_balanced():
    x = [bytes([i]) for i in range(4)]
    expected = N(N(L(x[0]), L(x[1])), N(L(x[2]), L(x[3])))
    assert merkle_root(x) == expected


def test_five_leaf_root_splits_four_then_one():
    x = [bytes([i]) for i in range(5)]
    left = N(N(L(x[0]), L(x[1])), N(L(x[2]), L(x[3])))
    assert merkle_root(x) == N(left, L(x[4]))


def test_six_leaf_root_splits_four_then_two():
    x = [bytes([i]) for i in range(6)]
    left = N(N(L(x[0]), L(x[1])), N(L(x[2]), L(x[3])))
    right = N(L(x[4]), L(x[5]))
    assert merkle_root(x) == N(left, right)


def test_seven_leaf_root_splits_four_then_two_then_one():
    x = [bytes([i]) for i in range(7)]
    left = N(N(L(x[0]), L(x[1])), N(L(x[2]), L(x[3])))
    right = N(N(L(x[4]), L(x[5])), L(x[6]))
    assert merkle_root(x) == N(left, right)


# --- proofs, pinned by hand ----------------------------------------------------

def test_the_audit_path_for_a_four_leaf_tree_is_the_expected_siblings():
    x = [bytes([i]) for i in range(4)]
    # Proving leaf 0: sibling leaf 1, then the right subtree over leaves 2 and 3.
    expected = [L(x[1]), N(L(x[2]), L(x[3]))]
    assert inclusion_proof(x, 0) == expected


def test_the_audit_path_for_leaf_two_of_four():
    x = [bytes([i]) for i in range(4)]
    expected = [L(x[3]), N(L(x[0]), L(x[1]))]
    assert inclusion_proof(x, 2) == expected


def test_the_audit_path_for_the_odd_leaf_of_three():
    x = [b"a", b"b", b"c"]
    expected = [N(L(b"a"), L(b"b"))]
    assert inclusion_proof(x, 2) == expected


def test_proof_length_is_logarithmic_and_exact():
    # Proving leaf 0. Note n=3 needs TWO siblings (leaf 1, then leaf 2's subtree),
    # because the tree is N(N(L0,L1), L2). Proof length depends on the index in an
    # unbalanced tree, which is why the odd-leaf case below is length 1.
    for n, expected in ((1, 0), (2, 1), (3, 2), (4, 2), (8, 3), (64, 6)):
        assert len(inclusion_proof([bytes([i]) for i in range(n)], 0)) == expected, n


def test_proof_length_depends_on_the_index_in_an_unbalanced_tree():
    x = [b"a", b"b", b"c"]
    assert len(inclusion_proof(x, 0)) == 2
    assert len(inclusion_proof(x, 1)) == 2
    assert len(inclusion_proof(x, 2)) == 1


# --- adversarial cases the existing suite does not cover -----------------------

def test_a_reordered_proof_fails():
    x = [f"l{i}".encode() for i in range(8)]
    r = merkle_root(x)
    assert not verify_inclusion(x[3], 3, 8, list(reversed(inclusion_proof(x, 3))), r)


def test_a_truncated_proof_fails():
    x = [f"l{i}".encode() for i in range(8)]
    r = merkle_root(x)
    assert not verify_inclusion(x[3], 3, 8, inclusion_proof(x, 3)[:-1], r)


def test_an_extended_proof_fails():
    x = [f"l{i}".encode() for i in range(8)]
    r = merkle_root(x)
    assert not verify_inclusion(x[3], 3, 8,
                                inclusion_proof(x, 3) + [b"\x00" * 32], r)


def test_a_flipped_bit_in_the_proof_fails():
    x = [f"l{i}".encode() for i in range(8)]
    r = merkle_root(x)
    proof = list(inclusion_proof(x, 3))
    b = bytearray(proof[0])
    b[0] ^= 0x01
    proof[0] = bytes(b)
    assert not verify_inclusion(x[3], 3, 8, proof, r)


def test_a_declared_size_of_zero_is_refused_not_accepted():
    x = [b"a", b"b", b"c"]
    assert not verify_inclusion(x[0], 0, 0, inclusion_proof(x, 0), merkle_root(x))


def test_a_size_larger_than_the_real_tree_fails():
    x = [f"l{i}".encode() for i in range(8)]
    r = merkle_root(x)
    assert not verify_inclusion(x[3], 3, 16, inclusion_proof(x, 3), r)


def test_a_proof_from_a_different_tree_of_the_same_size_fails():
    a = [f"a{i}".encode() for i in range(8)]
    b = [f"b{i}".encode() for i in range(8)]
    assert not verify_inclusion(a[3], 3, 8, inclusion_proof(b, 3), merkle_root(a))


def test_root_hex_is_tagged_and_full_length():
    tag, hexd = root_hex([b"a", b"b"]).split(":", 1)
    assert tag == "sha256" and len(hexd) == 64
    assert bytes.fromhex(hexd) == merkle_root([b"a", b"b"])
