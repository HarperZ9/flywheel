"""receipt_proof.py -- the receipts-proof/v2 wire contract.

One strict object a stranger can verify offline: schema, leaf, index,
tree_size, merkle_root, audit_path, where every audit step is exactly
{"hash": 64-hex, "side": "left" | "right"}. The desktop recomputes the
root in pure Dart before any MATCH label; this module normalizes what
the gateway serves so Python and Dart share one shape and one
vocabulary. Zero dependencies; errors carry fixed messages and never
echo candidate-controlled text beyond the caller's own leaf.
"""
from __future__ import annotations

from harness.transparency_log import inclusion_proof, merkle_root

SCHEMA = "flywheel.receipts-proof/v2"
_SIDES = ("left", "right")
_HEX = set("0123456789abcdef")


class ReceiptProofError(ValueError):
    """A malformed proof request; message is fixed, never candidate text."""


class LeafNotFound(ReceiptProofError):
    """The leaf is well formed but absent from this log."""


def _hex64(leaf: str) -> str:
    if not isinstance(leaf, str) or len(leaf) != 64 or not set(leaf) <= _HEX:
        raise ReceiptProofError(
            "a Merkle leaf is a 64-hex sha256 envelope digest")
    return leaf


def _step(raw: dict) -> dict:
    if not isinstance(raw, dict) or set(raw) != {"hash", "side"}:
        raise ReceiptProofError("audit steps carry exactly hash and side")
    h, side = raw["hash"], raw["side"]
    if (not isinstance(h, str) or len(h) != 64 or not set(h) <= _HEX
            or side not in _SIDES):
        raise ReceiptProofError("audit steps carry exactly hash and side")
    return {"hash": h, "side": side}


def build_receipt_proof(leaf: str, leaves: list) -> dict:
    """The full v2 wire object for `leaf` inside `leaves`.

    Raises ReceiptProofError (fixed message) for a malformed leaf and
    LeafNotFound when a well-formed leaf is not in the log.
    """
    leaf = _hex64(leaf)
    if leaf not in leaves:
        raise LeafNotFound("leaf not in the receipts log")
    idx = leaves.index(leaf)
    return {
        "schema": SCHEMA,
        "leaf": leaf,
        "index": idx,
        "tree_size": len(leaves),
        "merkle_root": merkle_root(leaves),
        "audit_path": [_step(s) for s in inclusion_proof(leaves, idx)],
    }


def route_payload(leaf: str, leaves: list) -> tuple[dict, int]:
    """Map a proof request onto (body, status) for the gateway route."""
    try:
        return build_receipt_proof(leaf, leaves), 200
    except LeafNotFound:
        root = merkle_root(leaves) if leaves else ""
        return ({"error": "leaf not in the receipts log",
                 "leaf": _hex64(leaf), "merkle_root": root}, 404)
    except ReceiptProofError as e:
        return {"error": str(e)}, 400
