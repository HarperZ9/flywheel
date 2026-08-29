"""anchor.py -- bind a signed tree head to an external timestamp over one digest.

The signed tree head (`tree_head.py`) stops the log's append-only claim from being
merely our word. It does not answer "before when": a signature says who, not when.
The external anchor answers when, by committing one digest into a public timeline
whose ordering no single party controls. The default timeline is Bitcoin, reached
through OpenTimestamps; a Zenodo DOI is the durability dual anchor. This module is
the seam between the two: it computes the exact digest that both the timestamp and
a later verifier agree on, and it verifies a head and its timestamp together.

The digest is `sha256` over the canonical bytes of the whole signed head,
signature included. So the timestamp proves that this head, signed by this key,
existed before the anchoring block. A stranger recomputes the same digest from the
signed head they hold and checks the OpenTimestamps proof starts from it; nothing
here is taken on trust from the record.

Like the tree head, this module never touches private key material: signing is a
caller-supplied callable. Like the stranger's verifier, `verify_anchor` raises
nothing; a bad head or a bad proof is a named reason, not an exception.
"""
from __future__ import annotations

import hashlib

from . import ots_verify, tree_head
from .receipt_fields import canonical

SCHEMA = "flywheel.anchor/v1"


def anchor_digest(signed_head: dict) -> tuple[str, bytes]:
    """The digest a timestamp covers: sha256 over the canonical signed head.

    Returns (`"sha256:"`-prefixed hex, raw 32 bytes). The raw bytes are what an
    OpenTimestamps proof starts from; the prefixed string is what a record shows.
    """
    raw = hashlib.sha256(canonical(signed_head).encode()).digest()
    return "sha256:" + raw.hex(), raw


def build_anchor(signed_head: dict) -> dict:
    """Assemble the anchor record for a head that is already signed."""
    prefixed, raw = anchor_digest(signed_head)
    return {
        "schema": SCHEMA,
        "signed_head": signed_head,
        "anchor_digest": prefixed,
        "digest_hex": raw.hex(),
        "does_not_prove": does_not_prove(),
    }


def sign_and_anchor(head: dict, sign, *, public_key: bytes, timestamp: str) -> dict:
    """Sign `head` (from `Ledger.head()`) and assemble its anchor record.

    `sign` is the same callable `tree_head.sign_head` takes: bytes -> 64 bytes.
    `timestamp` is the head's own attestation time, supplied by the caller; it is
    not the external timestamp, which is obtained afterward by stamping
    `digest_hex` and recorded once the proof upgrades to a block.
    """
    signed = tree_head.sign_head(head, sign, public_key=public_key,
                                 timestamp=timestamp)
    return build_anchor(signed)


def verify_anchor(anchor: dict, public_key: bytes, *, ots_bytes: bytes = None,
                  header_provider=None) -> dict:
    """(dict) Check the signed head and, if given, its timestamp, together.

    The key is an argument, never read from the record. Without `ots_bytes` the
    head is checked and the timestamp reported absent, which is honest rather than
    a pass. `ok` requires both a good head and a Bitcoin-verified timestamp over
    this record's digest.
    """
    result = {"ok": False, "head_ok": False, "head_reason": "",
              "anchor_digest": None, "timestamp": "absent"}
    if not isinstance(anchor, dict) or not isinstance(anchor.get("signed_head"), dict):
        result["head_reason"] = "malformed_anchor: no signed_head"
        return result
    signed = anchor["signed_head"]
    head_ok, head_reason = tree_head.check_signed_head(signed, public_key)
    result["head_ok"], result["head_reason"] = head_ok, head_reason
    try:
        prefixed, raw = anchor_digest(signed)
    except ValueError as e:
        # json.loads accepts NaN/Infinity, but canonical() forbids them
        # (allow_nan=False). A record whose signed_head carries a non-finite float
        # cannot be canonicalized: name it, do not let the verifier raise.
        result["head_reason"] = f"malformed_anchor: non-canonical head ({e})"
        return result
    result["anchor_digest"] = prefixed
    if ots_bytes is not None:
        result["timestamp"] = ots_verify.verify(ots_bytes, raw, header_provider)
    if head_ok and isinstance(result["timestamp"], dict) and result["timestamp"]["ok"]:
        result["ok"] = True
    return result


def does_not_prove() -> list[str]:
    """What an anchored head still does not establish."""
    return tree_head.does_not_prove() + [
        "NOT_PROVES_BEFORE_ANY_TIME_UNTIL_CONFIRMED: an OpenTimestamps proof only "
        "bounds time once it has upgraded into a Bitcoin block. A pending proof "
        "names a calendar that promised to anchor it, which is not yet a block.",
        "NOT_PROVES_THE_DIGEST_IS_MEANINGFUL: the timestamp bounds when these "
        "bytes existed, not that the head they carry is honest about the tree.",
        "NOT_PROVES_THE_HEADER_IS_A_REAL_BLOCK: the offline proof-of-work recheck "
        "confirms a bundle-carried header is internally consistent and clears a "
        "real target, which refuses a zero-work forgery. It does not establish "
        "that the header sits on the real Bitcoin chain; a header is only as "
        "trustworthy as its source. Cross-check the block hash against an "
        "independent chain view for linkage, not just this internal recheck.",
    ]
