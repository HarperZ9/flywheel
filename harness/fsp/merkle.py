"""Merkle tree hashing and proofs as RFC 9162 section 2.1 defines them.

Leaf hash: SHA-256(0x00 || d). Node hash: SHA-256(0x01 || left || right).
Proof generation follows the PATH and SUBPROOF definitions; verification
follows the algorithms of sections 2.1.3.2 and 2.1.4.2.
"""

from __future__ import annotations

import hashlib

EMPTY_ROOT = hashlib.sha256(b"").digest()


def leaf_hash(data: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    """Largest power of two strictly smaller than n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


class MerkleTree:
    """Append-only list of leaf hashes with cached subtree hashes."""

    def __init__(self) -> None:
        self.leaves: list[bytes] = []
        self._cache: dict[tuple[int, int], bytes] = {}

    def append(self, data: bytes) -> int:
        self.leaves.append(leaf_hash(data))
        return len(self.leaves) - 1

    def append_hash(self, lh: bytes) -> int:
        self.leaves.append(lh)
        return len(self.leaves) - 1

    def _mth(self, lo: int, hi: int) -> bytes:
        n = hi - lo
        if n == 0:
            return EMPTY_ROOT
        if n == 1:
            return self.leaves[lo]
        hit = self._cache.get((lo, hi))
        if hit is not None:
            return hit
        k = _split(n)
        value = node_hash(self._mth(lo, lo + k), self._mth(lo + k, hi))
        self._cache[(lo, hi)] = value
        return value

    def root(self, size: int | None = None) -> bytes:
        size = len(self.leaves) if size is None else size
        if size > len(self.leaves):
            raise ValueError("size beyond the tree")
        return self._mth(0, size)

    def inclusion_proof(self, index: int, size: int) -> list[bytes]:
        if not 0 <= index < size <= len(self.leaves):
            raise ValueError("index or size out of range")
        return self._path(index, 0, size)

    def _path(self, m: int, lo: int, hi: int) -> list[bytes]:
        n = hi - lo
        if n == 1:
            return []
        k = _split(n)
        if m < k:
            return self._path(m, lo, lo + k) + [self._mth(lo + k, hi)]
        return self._path(m - k, lo + k, hi) + [self._mth(lo, lo + k)]

    def consistency_proof(self, old: int, new: int) -> list[bytes]:
        if not 0 < old <= new <= len(self.leaves):
            raise ValueError("sizes out of range")
        if old == new:
            return []
        return self._subproof(old, 0, new, True)

    def _subproof(self, m: int, lo: int, hi: int, whole: bool) -> list[bytes]:
        n = hi - lo
        if m == n:
            return [] if whole else [self._mth(lo, hi)]
        k = _split(n)
        if m <= k:
            return self._subproof(m, lo, lo + k, whole) + [self._mth(lo + k, hi)]
        return self._subproof(m - k, lo + k, hi, False) + [self._mth(lo, lo + k)]


def verify_inclusion(lh: bytes, index: int, size: int, proof: list[bytes], root: bytes) -> bool:
    """RFC 9162 section 2.1.3.2."""
    if index >= size or index < 0:
        return False
    fn, sn, r = index, size - 1, lh
    for p in proof:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root


def verify_consistency(old: int, new: int, old_root: bytes, new_root: bytes,
                       proof: list[bytes]) -> bool:
    """RFC 9162 section 2.1.4.2."""
    if old <= 0 or old > new:
        return False
    if old == new:
        return not proof and old_root == new_root
    if old & (old - 1) == 0:
        proof = [old_root] + list(proof)
    if not proof:
        return False
    fn, sn = old - 1, new - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = proof[0]
    for c in proof[1:]:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr = node_hash(c, fr)
            sr = node_hash(c, sr)
            while not fn & 1 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            sr = node_hash(sr, c)
        fn >>= 1
        sn >>= 1
    return fr == old_root and sr == new_root and sn == 0
