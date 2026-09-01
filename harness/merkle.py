"""merkle.py — an RFC 6962 / RFC 9162 style Merkle tree for receipt corpora (zero-dep).

The projected world hashes its receipts into one root. A flat concat-hash proves the
whole set at once but cannot prove a SINGLE receipt without rehashing everything. A
Merkle tree fixes that: a compact audit path (log n sibling hashes) proves one leaf
is in the tree, so a stranger verifies one receipt offline in log n work regardless
of corpus size, and any tampering moves the root.

Domain-separated hashing (leaves prefixed 0x00, internal nodes 0x01) is the standard
that prevents second-preimage attacks. Standard library (hashlib) only.
"""
from __future__ import annotations

import hashlib


def _sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf_hash(data: bytes) -> bytes:
    return _sha(b"\x00" + data)


def _node(left: bytes, right: bytes) -> bytes:
    return _sha(b"\x01" + left + right)


def _largest_pow2_below(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _mth(hashes: list) -> bytes:
    """Merkle Tree Hash over already-leaf-hashed values (RFC 6962)."""
    n = len(hashes)
    if n == 0:
        return _sha(b"")
    if n == 1:
        return hashes[0]
    k = _largest_pow2_below(n)
    return _node(_mth(hashes[:k]), _mth(hashes[k:]))


def merkle_root(leaves: list) -> bytes:
    """Root over a list of raw leaf byte-strings."""
    return _mth([leaf_hash(x) for x in leaves])


def _proof(hashes: list, m: int) -> list:
    n = len(hashes)
    if n <= 1:
        return []
    k = _largest_pow2_below(n)
    if m < k:
        return _proof(hashes[:k], m) + [_mth(hashes[k:])]
    return _proof(hashes[k:], m - k) + [_mth(hashes[:k])]


def inclusion_proof(leaves: list, index: int) -> list:
    """The audit path (sibling hashes, leaf-level first) proving leaves[index]."""
    if not 0 <= index < len(leaves):
        raise IndexError("index out of range")
    return _proof([leaf_hash(x) for x in leaves], index)


def _root_from_proof(target: bytes, m: int, n: int, proof: list) -> bytes:
    if n <= 1:
        return target
    k = _largest_pow2_below(n)
    if m < k:
        return _node(_root_from_proof(target, m, k, proof[:-1]), proof[-1])
    return _node(proof[-1], _root_from_proof(target, m - k, n - k, proof[:-1]))


def verify_inclusion(leaf_data: bytes, index: int, size: int, proof: list,
                     root: bytes) -> bool:
    """Recompute the root from one leaf + its audit path; True iff it matches. Needs
    only (leaf, index, size, proof, root), never the whole leaf set."""
    if not isinstance(size, int) or not isinstance(index, int) \
            or not isinstance(proof, list):
        return False
    if size <= 0 or not 0 <= index < size or len(proof) != _proof_len(size, index):
        return False
    return _root_from_proof(leaf_hash(leaf_data), index, size, proof) == root


def _proof_len(n: int, m: int) -> int:
    if n <= 1:
        return 0
    k = _largest_pow2_below(n)
    return (_proof_len(k, m) if m < k else _proof_len(n - k, m - k)) + 1


def root_hex(leaves: list) -> str:
    return "sha256:" + merkle_root(leaves).hex()


# --- consistency proofs (RFC 6962 section 2.1.2) -----------------------------
#
# An inclusion proof answers "is this leaf in that tree" and says nothing about
# whether the tree was rewritten. A consistency proof answers the other question:
# given an OLD root a stranger already holds, does the NEW tree contain the old
# tree unchanged as a prefix?
#
# That is the difference between append-only as a policy and append-only as a
# property. Without it a maintainer can rebuild the log with an entry removed and
# every inclusion proof for the surviving entries still verifies against the new
# root.
#
# The verifier below is a RECURSIVE MIRROR of the generator rather than the usual
# iterative bit-twiddling formulation. Both are correct; this one can be checked
# against the RFC's SUBPROOF definition line by line, and the iterative version
# is where implementations go wrong.


class MerkleError(ValueError):
    """A proof request or check that is not well posed.

    Distinct from returning False: "this is not a growth claim" (old size larger
    than new, old size zero) and "this growth claim is invalid" are different
    facts, and collapsing them hides which one happened.
    """


def _subproof(hashes: list, m: int, b: bool) -> list:
    """RFC 6962 SUBPROOF(m, D[n], b) over already-leaf-hashed values."""
    n = len(hashes)
    if m == n:
        # The old tree is exactly this subtree. At the root position the verifier
        # already holds its hash, so nothing is emitted; elsewhere it is needed.
        return [] if b else [_mth(hashes)]
    k = _largest_pow2_below(n)
    if m <= k:
        return _subproof(hashes[:k], m, b) + [_mth(hashes[k:])]
    return _subproof(hashes[k:], m - k, False) + [_mth(hashes[:k])]


def consistency_proof(leaves: list, old_size: int) -> list:
    """The proof that a tree over `leaves` contains its own first `old_size`
    leaves unchanged as a prefix."""
    n = len(leaves)
    if not isinstance(old_size, int) or old_size <= 0:
        raise MerkleError(f"old_size must be a positive integer, got {old_size!r}")
    if old_size > n:
        raise MerkleError(
            f"old_size {old_size} exceeds the tree size {n}: a log cannot have "
            "shrunk and still be append-only")
    if old_size == n:
        return []
    return _subproof([leaf_hash(x) for x in leaves], old_size, True)


def _reconstruct(m: int, n: int, proof: list, b: bool,
                 old_root: bytes) -> tuple:
    """Rebuild (old_subtree_hash, new_subtree_hash) consuming `proof` from the
    end, exactly mirroring _subproof. Returns the remaining proof."""
    if m == n:
        if b:
            return old_root, old_root, proof
        if not proof:
            raise _ProofExhausted()
        h = proof[-1]
        return h, h, proof[:-1]
    k = _largest_pow2_below(n)
    if not proof:
        raise _ProofExhausted()
    if m <= k:
        right = proof[-1]
        lo, ln, rest = _reconstruct(m, k, proof[:-1], b, old_root)
        return lo, _node(ln, right), rest
    left = proof[-1]
    ro, rn, rest = _reconstruct(m - k, n - k, proof[:-1], False, old_root)
    return _node(left, ro), _node(left, rn), rest


class _ProofExhausted(Exception):
    """A proof too short to rebuild the claimed shape. Internal; surfaces as
    False, because a short proof is an invalid claim rather than a malformed
    request."""


def verify_consistency(old_size: int, new_size: int, old_root: bytes,
                       new_root: bytes, proof: list) -> bool:
    """True iff the tree with `new_root` contains the tree with `old_root` as an
    unmodified prefix of `old_size` leaves.

    Raises MerkleError when the claim is not well posed (a shrinking log, a
    non-positive old size). Returns False when the claim is well posed and wrong.
    """
    if not isinstance(old_size, int) or not isinstance(new_size, int):
        raise MerkleError("sizes must be integers")
    if old_size <= 0:
        raise MerkleError("old_size must be positive")
    if old_size > new_size:
        raise MerkleError(
            f"old_size {old_size} exceeds new_size {new_size}: that is a "
            "truncation claim, not a growth claim, and it is refused rather than "
            "reported as merely invalid")
    if old_size == new_size:
        return not proof and old_root == new_root
    try:
        lo, ln, rest = _reconstruct(old_size, new_size, list(proof), True,
                                    old_root)
    except _ProofExhausted:
        return False
    if rest:
        return False                    # unused proof elements: not this shape
    return lo == old_root and ln == new_root
