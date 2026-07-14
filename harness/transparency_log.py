"""transparency_log.py -- receipts provable without the whole ledger.

A Merkle tree over envelope hashes: the root is one 64-hex commitment
to every receipt beneath it, and an inclusion proof lets a stranger
verify that one receipt is in the log by walking named siblings, never
by trusting the log's keeper. Leaves are domain-separated from interior
nodes (the standard second-preimage guard), odd nodes promote, and an
empty log has no root because a commitment to nothing is a lie waiting
for content. Zero dependencies, pure functions; persistence composes
with the store's audit chain rather than replacing it.
"""
from __future__ import annotations

import hashlib

_LEAF = b"\x00"
_NODE = b"\x01"


def _h(prefix: bytes, *parts: bytes) -> str:
    m = hashlib.sha256()
    m.update(prefix)
    for p in parts:
        m.update(p)
    return m.hexdigest()


def _level(leaves: list) -> list:
    return [_h(_LEAF, bytes.fromhex(x)) for x in leaves]


def merkle_root(leaves: list) -> str:
    """The root commitment over leaf hashes (64-hex strings)."""
    if not leaves:
        raise ValueError("an empty log has no root")
    level = _level(leaves)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                nxt.append(_h(_NODE, bytes.fromhex(level[i]),
                              bytes.fromhex(level[i + 1])))
            else:
                nxt.append(level[i])          # odd node promotes
        level = nxt
    return level[0]


def inclusion_proof(leaves: list, index: int) -> list:
    """The sibling path for leaves[index]: a list of {"hash", "side"}
    where side names which side the sibling sits on."""
    if not 0 <= index < len(leaves):
        raise ValueError(f"no leaf at index {index}")
    level = _level(leaves)
    path = []
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                if i == index or i + 1 == index:
                    sib = i + 1 if i == index else i
                    path.append({"hash": level[sib],
                                 "side": "right" if sib > index else "left"})
                nxt.append(_h(_NODE, bytes.fromhex(level[i]),
                              bytes.fromhex(level[i + 1])))
            else:
                nxt.append(level[i])
        index //= 2
        level = nxt
    return path


def verify_inclusion(leaf: str, proof: list, root: str) -> bool:
    """Walk the sibling path from a leaf hash; True iff it lands on root."""
    try:
        cur = _h(_LEAF, bytes.fromhex(leaf))
        for step in proof:
            sib = bytes.fromhex(step["hash"])
            if step.get("side") == "left":
                cur = _h(_NODE, sib, bytes.fromhex(cur))
            else:
                cur = _h(_NODE, bytes.fromhex(cur), sib)
    except (ValueError, KeyError, TypeError):
        return False
    return cur == root
