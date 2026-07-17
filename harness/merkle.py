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
