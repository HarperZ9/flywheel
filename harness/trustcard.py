"""trustcard.py — detached signature + machine-readable trust card for wiki nodes.

A plain content hash proves integrity to anyone who can recompute it; it does NOT
prove WHO sealed it. A detached HMAC signature does: only a holder of the signing
key can produce it, so a node's seal is attributable to our harness, and any edit
(or a forged node without the key) fails verification. Paired with a TrustCard —
author, provenance verdict, freshness, scan status, signature — this is the
"inline trust rendering" the dive named (NVIDIA-Verified-Skills SKILLCARD), so
trust metadata is visible at point of use, not buried in a registry.

Honest labeling: this is an HMAC (symmetric — integrity + signer-authenticity
under a shared key), NOT a public-key signature (no non-repudiation to third
parties). For local provenance that is the right, zero-dependency tool; a real
detached OMS/PKI signature is the upgrade if third-party verification is needed.
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass


def sign(content: str, key: bytes) -> str:
    """Detached HMAC-SHA256 signature over content."""
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_sig(content: str, signature: str, key: bytes) -> bool:
    """Constant-time verify. False on any tamper or wrong key."""
    return hmac.compare_digest(sign(content, key), signature or "")


@dataclass
class TrustCard:
    node_id: str
    author: str
    provenance: str          # SEALED | UNVERIFIABLE (from the node)
    source_ref: str
    freshness: str           # MATCH | DRIFT | UNVERIFIABLE (last verify result)
    scan_status: str         # e.g. "clean" | "unscanned"
    signature: str

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("node_id", "author", "provenance", "source_ref", "freshness",
                 "scan_status", "signature")}


def _node_seal_content(node) -> str:
    """The exact bytes a node's trust is over: id + kind + source + hash + tier."""
    return "|".join([str(node.id), str(node.kind), str(node.source_ref),
                     str(node.source_hash), str(getattr(node, "tier", ""))])


def make_trustcard(node, key: bytes, *, author: str, freshness: str = "UNVERIFIABLE",
                   scan_status: str = "unscanned") -> TrustCard:
    content = _node_seal_content(node)
    return TrustCard(
        node_id=node.id, author=author, provenance=node.provenance,
        source_ref=node.source_ref, freshness=freshness, scan_status=scan_status,
        signature=sign(content, key))


def verify_trustcard(node, card: TrustCard, key: bytes) -> str:
    """MATCH (signature valid over the current node), TAMPERED (signature present
    but no longer valid — the node or card changed), UNSIGNED (no signature)."""
    if not card.signature:
        return "UNSIGNED"
    return "MATCH" if verify_sig(_node_seal_content(node), card.signature, key) else "TAMPERED"
