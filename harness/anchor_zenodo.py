"""anchor_zenodo.py -- deposit the durability DOI over the SAME bytes the Bitcoin
leg timestamps, so the two anchors witness one fact.

`anchor.py` computes a single digest: sha256 over the canonical signed head. The
OpenTimestamps proof covers that digest. For a Zenodo DOI to be a second,
independent witness rather than an unrelated upload, the file behind the DOI must
be exactly those canonical bytes. Then a stranger downloads the DOI's file, hashes
it, gets the digest, and checks that the OpenTimestamps proof starts from the same
digest. Two witnesses, one digest, no shared trust root.

This module is the seam on the producer side. `deposit_bytes` turns an anchor
record into the exact (name, bytes) to deposit and refuses a record whose stored
digest disagrees with its own head, so a corrupted or tampered record never
reaches the network. `check_binding` is the stranger's side: does this file hash
to this record's digest. `deposit_anchor` wires the bytes through
`zenodo_deposit.deposit`, keeping that module's irreversible-publish guard.

Like `anchor_submit.py` (the Bitcoin leg's producer), this leg is thin: it decides
the bytes and delegates the network. Failures route through `DepositError`, the
one taxonomy the deposit path already uses.
"""
from __future__ import annotations

import hashlib

from . import zenodo_deposit
from .receipt_fields import canonical
from .zenodo_deposit import DepositError

_FILENAME = "signed-head.json"


def _head_bytes(anchor: dict) -> bytes:
    """The canonical signed-head bytes the record carries, or a `DepositError`."""
    signed = anchor.get("signed_head") if isinstance(anchor, dict) else None
    if not isinstance(signed, dict):
        raise DepositError("anchor record has no signed_head")
    return canonical(signed).encode()


def deposit_bytes(anchor: dict) -> tuple[str, bytes]:
    """The exact (name, bytes) to deposit for `anchor`: its canonical signed head.

    The record is checked for internal consistency first. The record carries the
    digest twice, as `digest_hex` (bare) and `anchor_digest` ("sha256:"-prefixed);
    both must equal the sha256 of the canonical head the record carries. If either
    disagrees, the record was corrupted or tampered, and depositing it would bind a
    DOI to bytes no anchor actually covers. That is a `DepositError`, raised before
    any network call, so a tampered record never reaches the network.
    """
    data = _head_bytes(anchor)
    computed = hashlib.sha256(data).hexdigest()
    stored = anchor.get("digest_hex")
    if computed != stored:
        raise DepositError(
            "anchor record is inconsistent: digest_hex does not match its "
            f"signed_head (stored {stored!r}, head hashes to {computed!r})")
    prefixed = anchor.get("anchor_digest")
    if prefixed is not None and prefixed != "sha256:" + computed:
        raise DepositError(
            "anchor record is inconsistent: anchor_digest does not match its "
            f"signed_head (stored {prefixed!r}, head hashes to 'sha256:{computed}')")
    return _FILENAME, data


def check_binding(file_bytes: bytes, anchor: dict) -> tuple[bool, str]:
    """(bool, reason) Does `file_bytes` hash to this anchor's head-derived digest.

    The stranger's check, and it trusts nothing the record self-reports. The
    authoritative digest is re-derived from the record's own signed head, the same
    way `anchor.verify_anchor` and the OpenTimestamps proof are anchored to it, not
    read from the record's `digest_hex` field. So a record whose digest field was
    edited to match forged bytes is still refused. This does not validate the
    timestamp; it only ties the DOI's bytes to the head-derived digest.
    """
    try:
        want = hashlib.sha256(_head_bytes(anchor)).hexdigest()
    except DepositError as e:
        return False, str(e)
    got = hashlib.sha256(bytes(file_bytes)).hexdigest()
    if got == want:
        return True, f"sha256 matches the head-derived anchor digest {got}"
    return False, f"sha256 mismatch: file is {got}, head-derived digest is {want}"


def deposit_anchor(request, anchor: dict, *, token: str, metadata: dict,
                   sandbox: bool = False, publish: bool = False) -> dict:
    """Deposit the bound bytes for `anchor` through `zenodo_deposit.deposit`.

    The bytes are `deposit_bytes(anchor)`, so the DOI covers exactly what the
    Bitcoin leg timestamps. The result carries the digest the DOI is bound to, so a
    caller can record "this DOI witnesses digest X" without recomputing it. Publish
    stays the caller's explicit, irreversible choice, guarded in `deposit`.
    """
    name, data = deposit_bytes(anchor)
    result = zenodo_deposit.deposit(
        request, token=token, files=[(name, data)], metadata=metadata,
        sandbox=sandbox, publish=publish)
    result["anchor_digest"] = anchor.get("anchor_digest")
    result["digest_hex"] = anchor.get("digest_hex")
    result["does_not_prove"] = list(result.get("does_not_prove") or []) + does_not_prove()
    return result


def does_not_prove() -> list[str]:
    """What binding the DOI to the digest still does not establish."""
    return [
        "NOT_PROVES_THE_TIMESTAMP: binding shows the DOI's file hashes to the "
        "anchor digest. Whether that digest was timestamped, and when, is the "
        "Bitcoin leg's separate proof; a DOI alone orders nothing.",
        "NOT_PROVES_ONE_DEPOSITOR: anyone holding the same signed head can deposit "
        "the same bytes and get their own DOI. The binding ties bytes to a digest, "
        "not a DOI to a sole author.",
    ]
