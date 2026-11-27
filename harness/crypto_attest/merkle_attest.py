# SPDX-License-Identifier: MIT
"""Pure-stdlib RFC 6962 Certificate Transparency Merkle proof verifier.

Implements SHA-256 Merkle tree root calculation, inclusion proofs, and
append-only consistency proofs with explicit domain separation (0x00 leaf
prefix, 0x01 internal node prefix) to prevent second-preimage confusion.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Sequence

HONEST_SCOPE_LIMIT = (
    "Verifies RFC 6962 SHA-256 Merkle inclusion and append-only consistency "
    "proofs with explicit 0x00/0x01 domain separation. Does not verify "
    "Signed Tree Head (STH) digital signatures or perform log gossip."
)

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"
DIGEST_BYTES = 32
EMPTY_TREE_HASH = hashlib.sha256(b"").digest()


def _largest_power_of_two_less_than(n: int) -> int:
    if n <= 1:
        raise ValueError("n must be greater than 1")
    return 1 << ((n - 1).bit_length() - 1)


def _check_digest(digest: bytes, label: str) -> bytes:
    if not isinstance(digest, (bytes, bytearray)) or len(digest) != DIGEST_BYTES:
        raise ValueError(f"{label} must be exactly {DIGEST_BYTES} bytes")
    return bytes(digest)


def leaf_hash(data: bytes) -> bytes:
    """Compute RFC 6962 leaf hash: SHA-256(0x00 || data)."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("leaf data must be bytes")
    return hashlib.sha256(LEAF_PREFIX + bytes(data)).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """Compute RFC 6962 interior node hash: SHA-256(0x01 || left || right)."""
    l_bytes = _check_digest(left, "left")
    r_bytes = _check_digest(right, "right")
    return hashlib.sha256(NODE_PREFIX + l_bytes + r_bytes).digest()


def _mth_hashes(leaf_hashes: Sequence[bytes]) -> bytes:
    n = len(leaf_hashes)
    if n == 0:
        return EMPTY_TREE_HASH
    if n == 1:
        return leaf_hashes[0]
    k = _largest_power_of_two_less_than(n)
    return node_hash(_mth_hashes(leaf_hashes[:k]), _mth_hashes(leaf_hashes[k:]))


def merkle_root(leaves: Sequence[bytes]) -> bytes:
    """Compute RFC 6962 Merkle Tree Hash (MTH) over raw leaf payloads."""
    return _mth_hashes([leaf_hash(item) for item in leaves])


def _inclusion_path(leaf_hashes: Sequence[bytes], index: int) -> list[bytes]:
    n = len(leaf_hashes)
    if n == 1:
        return []
    k = _largest_power_of_two_less_than(n)
    if index < k:
        return _inclusion_path(leaf_hashes[:k], index) + [_mth_hashes(leaf_hashes[k:])]
    return _inclusion_path(leaf_hashes[k:], index - k) + [_mth_hashes(leaf_hashes[:k])]


def inclusion_proof(leaves: Sequence[bytes], index: int) -> list[bytes]:
    """Generate RFC 6962 inclusion proof for leaf at index."""
    n = len(leaves)
    if index < 0 or index >= n:
        raise IndexError(f"leaf index {index} out of range for tree_size {n}")
    return _inclusion_path([leaf_hash(item) for item in leaves], index)


def verify_inclusion(
    leaf_data: bytes,
    index: int,
    tree_size: int,
    proof: Sequence[bytes],
    expected_root: bytes,
) -> bool:
    """Verify an RFC 6962 inclusion proof fail-closed in constant time."""
    if not isinstance(leaf_data, (bytes, bytearray)):
        return False
    if tree_size <= 0 or index < 0 or index >= tree_size:
        return False
    if not isinstance(expected_root, (bytes, bytearray)) or len(expected_root) != DIGEST_BYTES:
        return False

    fn = index
    sn = tree_size - 1
    current = leaf_hash(bytes(leaf_data))
    for sibling in proof:
        if not isinstance(sibling, (bytes, bytearray)) or len(sibling) != DIGEST_BYTES:
            return False
        if sn == 0:
            return False
        sib = bytes(sibling)
        if (fn & 1) or (fn == sn):
            current = node_hash(sib, current)
            while fn != 0 and (fn & 1) == 0:
                fn >>= 1
                sn >>= 1
        else:
            current = node_hash(current, sib)
        fn >>= 1
        sn >>= 1

    return sn == 0 and hmac.compare_digest(current, bytes(expected_root))


def _subproof(leaf_hashes: Sequence[bytes], first: int, complete: bool) -> list[bytes]:
    n = len(leaf_hashes)
    if first == n:
        return [] if complete else [_mth_hashes(leaf_hashes)]
    k = _largest_power_of_two_less_than(n)
    if first <= k:
        return _subproof(leaf_hashes[:k], first, complete) + [_mth_hashes(leaf_hashes[k:])]
    return _subproof(leaf_hashes[k:], first - k, False) + [_mth_hashes(leaf_hashes[:k])]


def consistency_proof(leaves: Sequence[bytes], first: int, second: int) -> list[bytes]:
    """Generate RFC 6962 append-only consistency proof from size first to second."""
    if first < 0 or second < 0 or first > second or second > len(leaves):
        raise ValueError(f"invalid consistency bounds: first={first}, second={second}, total={len(leaves)}")
    if first == 0 or first == second:
        return []
    hashes = [leaf_hash(item) for item in leaves[:second]]
    return _subproof(hashes, first, True)


def _walk_consistency(first: int, second: int, nodes: list[bytes]) -> tuple[bool, bytes, bytes]:
    fn, sn = first - 1, second - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    fr = sr = nodes[0]
    for node in nodes[1:]:
        if sn == 0:
            return False, fr, sr
        if (fn & 1) or (fn == sn):
            fr = node_hash(node, fr)
            sr = node_hash(node, sr)
            while fn != 0 and (fn & 1) == 0:
                fn >>= 1
                sn >>= 1
        else:
            sr = node_hash(sr, node)
        fn >>= 1
        sn >>= 1
    return sn == 0, fr, sr


def verify_consistency(
    first: int,
    second: int,
    first_root: bytes,
    second_root: bytes,
    proof: Sequence[bytes],
) -> bool:
    """Verify an RFC 6962 append-only consistency proof fail-closed."""
    if first < 0 or second < 0 or first > second:
        return False
    if not isinstance(first_root, (bytes, bytearray)) or len(first_root) != DIGEST_BYTES:
        return False
    if not isinstance(second_root, (bytes, bytearray)) or len(second_root) != DIGEST_BYTES:
        return False
    if any(not isinstance(p, (bytes, bytearray)) or len(p) != DIGEST_BYTES for p in proof):
        return False
    f_root, s_root = bytes(first_root), bytes(second_root)
    if first == 0:
        return len(proof) == 0 and hmac.compare_digest(f_root, EMPTY_TREE_HASH)
    if first == second:
        return len(proof) == 0 and hmac.compare_digest(f_root, s_root)
    if not proof:
        return False
    nodes = [bytes(p) for p in proof]
    if (first & (first - 1)) == 0:
        nodes = [f_root, *nodes]
    ok, fr, sr = _walk_consistency(first, second, nodes)
    return ok and hmac.compare_digest(fr, f_root) and hmac.compare_digest(sr, s_root)


def check_domain_separation(left: bytes, right: bytes) -> bool:
    """Confirm 64-byte leaf preimage cannot collide with 0x01 interior node."""
    l_bytes = _check_digest(left, "left")
    r_bytes = _check_digest(right, "right")
    return not hmac.compare_digest(leaf_hash(l_bytes + r_bytes), node_hash(l_bytes, r_bytes))
