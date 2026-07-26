"""Consistency proofs: append-only stops being my claim and becomes your check.

An inclusion proof answers "is this receipt in that tree". It says nothing about
whether the tree was ever rewritten. A consistency proof answers the other
question: given an OLD root a stranger already holds, does the NEW tree contain
that old tree unchanged as a prefix?

That is the whole difference between append-only as a policy and append-only as a
property. Without it, a maintainer can silently rebuild the log with an
embarrassing entry removed and every inclusion proof for the surviving entries
still verifies against the new root.

RFC 6962 section 2.1.2. The known-answer tests are the ones that matter, for the
same reason they mattered for the tree and for Ed25519: an implementation that
agrees only with itself passes every internal check while being wrong.
"""
import hashlib

import pytest

from harness.merkle import (
    merkle_root, leaf_hash, consistency_proof, verify_consistency, MerkleError,
)


def L(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def N(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _leaves(n, tag="l"):
    return [f"{tag}{i}".encode() for i in range(n)]


# --- the property, across many sizes -------------------------------------------

@pytest.mark.parametrize("old,new", [
    (1, 2), (1, 8), (2, 3), (2, 4), (3, 4), (3, 7), (4, 5), (4, 8),
    (5, 6), (5, 9), (6, 8), (7, 8), (8, 9), (8, 16), (9, 17), (13, 21),
])
def test_growing_the_log_yields_a_verifying_consistency_proof(old, new):
    leaves = _leaves(new)
    old_root = merkle_root(leaves[:old])
    new_root = merkle_root(leaves)
    proof = consistency_proof(leaves, old)
    assert verify_consistency(old, new, old_root, new_root, proof) is True, (old, new)


def test_a_tree_is_consistent_with_itself_with_an_empty_proof():
    leaves = _leaves(5)
    r = merkle_root(leaves)
    assert consistency_proof(leaves, 5) == []
    assert verify_consistency(5, 5, r, r, []) is True


# --- the attack it exists to catch ---------------------------------------------

def test_dropping_an_entry_while_the_log_keeps_growing_is_caught():
    """The whole point, modelled as the attack actually looks.

    The log had 6 entries. The maintainer wants entry 2 gone but cannot let the
    log shrink, because a shrinking log is refused outright. So they rebuild with
    entry 2 removed and two new entries appended: the log has GROWN from 6 to 7,
    every inclusion proof for the surviving entries verifies against the new root,
    and only a consistency proof against the old root catches it.
    """
    original = _leaves(6)
    old_root = merkle_root(original)
    doctored = original[:2] + original[3:] + [b"new-a", b"new-b"]
    assert len(doctored) == 7
    new_root = merkle_root(doctored)
    proof = consistency_proof(doctored, 6)
    assert verify_consistency(6, 7, old_root, new_root, proof) is False


def test_the_same_growth_with_an_untouched_prefix_verifies():
    """The control. Identical shape, prefix left alone, and it passes. Without
    this the test above would also pass for an implementation that always says no.
    """
    original = _leaves(6)
    honest = original + [b"new-a"]
    assert verify_consistency(6, 7, merkle_root(original), merkle_root(honest),
                              consistency_proof(honest, 6)) is True


def test_a_shrinking_log_is_refused_as_a_truncation_claim():
    original = _leaves(6)
    doctored = original[:2] + original[3:]
    with pytest.raises(MerkleError):
        verify_consistency(6, len(doctored), merkle_root(original),
                           merkle_root(doctored), [])


def test_replacing_an_entry_in_place_is_caught():
    original = _leaves(8)
    old_root = merkle_root(original[:4])
    doctored = list(original)
    doctored[1] = b"rewritten"
    assert verify_consistency(4, 8, old_root, merkle_root(doctored),
                              consistency_proof(doctored, 4)) is False


def test_reordering_the_prefix_is_caught():
    original = _leaves(8)
    old_root = merkle_root(original[:4])
    doctored = list(original)
    doctored[0], doctored[1] = doctored[1], doctored[0]
    assert verify_consistency(4, 8, old_root, merkle_root(doctored),
                              consistency_proof(doctored, 4)) is False


def test_truncating_the_log_is_caught():
    original = _leaves(8)
    old_root = merkle_root(original)
    short = original[:5]
    with pytest.raises(MerkleError):
        # A new size smaller than the old one is not a growth claim at all.
        verify_consistency(8, 5, old_root, merkle_root(short),
                           consistency_proof(short, 5))


# --- proof integrity ------------------------------------------------------------

def test_a_flipped_bit_in_the_proof_fails():
    leaves = _leaves(9)
    proof = list(consistency_proof(leaves, 4))
    b = bytearray(proof[0])
    b[0] ^= 0x01
    proof[0] = bytes(b)
    assert verify_consistency(4, 9, merkle_root(leaves[:4]),
                              merkle_root(leaves), proof) is False


def test_a_truncated_proof_fails():
    leaves = _leaves(9)
    proof = consistency_proof(leaves, 4)
    assert verify_consistency(4, 9, merkle_root(leaves[:4]),
                              merkle_root(leaves), proof[:-1]) is False


def test_an_extended_proof_fails():
    leaves = _leaves(9)
    proof = consistency_proof(leaves, 4) + [b"\x00" * 32]
    assert verify_consistency(4, 9, merkle_root(leaves[:4]),
                              merkle_root(leaves), proof) is False


def test_a_reordered_proof_fails():
    leaves = _leaves(16)
    proof = consistency_proof(leaves, 5)
    if len(proof) > 1:
        assert verify_consistency(5, 16, merkle_root(leaves[:5]),
                                  merkle_root(leaves),
                                  list(reversed(proof))) is False


def test_a_proof_from_a_different_log_fails():
    a = _leaves(9, "a")
    b = _leaves(9, "b")
    assert verify_consistency(4, 9, merkle_root(a[:4]), merkle_root(a),
                              consistency_proof(b, 4)) is False


def test_a_wrong_old_root_fails():
    leaves = _leaves(9)
    assert verify_consistency(4, 9, merkle_root(_leaves(4, "other")),
                              merkle_root(leaves),
                              consistency_proof(leaves, 4)) is False


def test_a_wrong_new_root_fails():
    leaves = _leaves(9)
    assert verify_consistency(4, 9, merkle_root(leaves[:4]),
                              merkle_root(_leaves(9, "other")),
                              consistency_proof(leaves, 4)) is False


# --- refusals -------------------------------------------------------------------

def test_an_old_size_of_zero_is_refused():
    leaves = _leaves(4)
    with pytest.raises(MerkleError):
        consistency_proof(leaves, 0)


def test_an_old_size_larger_than_the_tree_is_refused():
    with pytest.raises(MerkleError):
        consistency_proof(_leaves(4), 9)


def test_a_shrinking_claim_is_refused_not_returned_false():
    # Refusing rather than returning False distinguishes "this is not a growth
    # claim" from "this growth claim is invalid".
    with pytest.raises(MerkleError):
        verify_consistency(9, 4, b"\x00" * 32, b"\x00" * 32, [])


# --- known answers, computed by hand -------------------------------------------

def test_the_proof_from_one_to_two_is_the_second_leaf():
    leaves = [b"a", b"b"]
    assert consistency_proof(leaves, 1) == [L(b"b")]


def test_the_proof_from_two_to_three_is_the_third_leaf():
    leaves = [b"a", b"b", b"c"]
    # The old tree of 2 is a complete subtree, so only the new leaf is needed.
    assert consistency_proof(leaves, 2) == [L(b"c")]


def test_the_proof_from_three_to_four_names_the_boundary_nodes():
    leaves = [b"a", b"b", b"c", b"d"]
    # Old size 3 is NOT a complete subtree, so the proof must expose how the old
    # root was formed: leaf c, its sibling d, and the left subtree over a and b.
    proof = consistency_proof(leaves, 3)
    assert L(b"c") in proof
    assert L(b"d") in proof
    assert N(L(b"a"), L(b"b")) in proof
