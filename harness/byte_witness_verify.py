"""byte_witness_verify.py -- check a byte witness offline, on stdlib alone.

This is the half a stranger runs. It imports nothing outside the standard
library and this repository, it needs no network, and it never raises: hostile
input is a named verdict, because a verifier that crashes on a malformed record
tells the caller nothing about the record.

Three words, and they are not interchangeable:

    MATCH         every check that was asked for ran and reproduced
    TAMPERED      a check ran and the record does not hold
    UNVERIFIABLE  nothing could be checked: a malformed record, or bytes
                  nobody could produce

Reading the third as the second turns an archive nobody can reach into an
accusation. Reading it as the first turns it into a lie. So it is its own answer.

A record can be refuted without its bytes. A span that runs past the length the
record itself claims is a contradiction inside the record, and that is TAMPERED
on the record alone.
"""
from __future__ import annotations

from typing import Any, Callable

from .byte_witness import GENESIS, WITNESS_SCHEMA, does_not_prove
from .evidence_json import canonical_sha256
from .tool_call_receipt import MATCH, TAMPERED, UNVERIFIABLE, _digest_well_formed, _sha256_hex

VERIFY_SCHEMA = "flywheel.byte-witness-verification/v1"
CHAIN_SCHEMA = "flywheel.byte-witness-chain-verification/v1"

MALFORMED = "MALFORMED"
DIGEST_MISMATCH = "DIGEST_MISMATCH"
LENGTH_MISMATCH = "LENGTH_MISMATCH"
SPAN_OUT_OF_RANGE = "SPAN_OUT_OF_RANGE"
SPAN_MISMATCH = "SPAN_MISMATCH"
LINK_BROKEN = "LINK_BROKEN"
BYTES_UNAVAILABLE = "BYTES_UNAVAILABLE"
SIGNATURE_INVALID = "SIGNATURE_INVALID"
NO_SIGNER = "NO_SIGNER"


def _result(verdict: str, failure_class: str | None, detail: str) -> dict:
    return {"schema": VERIFY_SCHEMA, "verdict": verdict,
            "failure_class": failure_class, "detail": detail}


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _span_shape(span: Any) -> str | None:
    """A named problem with one span's shape, or None. Range is checked later."""
    if not isinstance(span, dict):
        return "a span is an object"
    if not _is_count(span.get("start")) or not _is_count(span.get("end")):
        return "a span is bounded by whole numbers"
    if not _digest_well_formed(str(span.get("sha256", ""))):
        return "a span carries a 64-character digest"
    if not isinstance(span.get("note", ""), str):
        return "a span note is text"
    return None


def _shape(record: Any) -> str | None:
    """A named problem with the record's shape, or None. Needs no bytes."""
    if not isinstance(record, dict):
        return "a witness record is an object"
    if record.get("schema") != WITNESS_SCHEMA:
        return f"record schema is not {WITNESS_SCHEMA}"
    if not isinstance(record.get("label"), str) or not record["label"]:
        return "a record names what its bytes are"
    if not _digest_well_formed(str(record.get("sha256", ""))):
        return "a record carries a 64-character digest"
    if not _is_count(record.get("length")):
        return "length is a whole number of bytes"
    if not isinstance(record.get("observed_at"), str):
        return "observed_at is text, and may be empty"
    prev = record.get("prev")
    if not isinstance(prev, str) or (prev != GENESIS and not _digest_well_formed(prev)):
        return "prev is empty at genesis, or the previous record's link"
    if not isinstance(record.get("spans"), list):
        return "spans is a list"
    if not isinstance(record.get("context"), dict):
        return "context is an object"
    for span in record["spans"]:
        problem = _span_shape(span)
        if problem is not None:
            return problem
    return None


def _self_contradiction(record: dict) -> str | None:
    """A record refuted by its own fields, without reference to any bytes."""
    for span in record["spans"]:
        if not span["start"] < span["end"] <= record["length"]:
            return (f"span [{span['start']}, {span['end']}) does not fit inside "
                    f"the {record['length']} bytes this record claims")
    return None


def _against_bytes(record: dict, data: bytes) -> dict:
    if len(data) != record["length"]:
        return _result(TAMPERED, LENGTH_MISMATCH,
                       f"record claims {record['length']} bytes, got {len(data)}")
    if _sha256_hex(data) != record["sha256"]:
        return _result(TAMPERED, DIGEST_MISMATCH,
                       "the bytes do not hash to the digest in the record")
    for span in record["spans"]:
        if _sha256_hex(data[span["start"]:span["end"]]) != span["sha256"]:
            return _result(TAMPERED, SPAN_MISMATCH,
                           f"span [{span['start']}, {span['end']}) does not hash "
                           "to the digest recorded for it")
    return _result(MATCH, None,
                   f"{record['length']} bytes and {len(record['spans'])} spans reproduced")


def verify_witness(record: Any, data: Any = None) -> dict:
    """Check one record, with its bytes when the caller has them.

    Without bytes the shape and the record's internal consistency are still
    checked, and the answer is UNVERIFIABLE rather than MATCH. A record that
    passed every check available to it has not passed the one that matters.
    """
    problem = _shape(record)
    if problem is not None:
        return _result(UNVERIFIABLE, MALFORMED, problem)
    contradiction = _self_contradiction(record)
    if contradiction is not None:
        return _result(TAMPERED, SPAN_OUT_OF_RANGE, contradiction)
    if data is None:
        return _result(UNVERIFIABLE, BYTES_UNAVAILABLE,
                       "the record is well formed and self-consistent; nothing "
                       "checked the bytes, because none were supplied")
    if isinstance(data, str) or not isinstance(data, (bytes, bytearray, memoryview)):
        return _result(UNVERIFIABLE, BYTES_UNAVAILABLE,
                       "bytes are checked against bytes; text has no bytes until "
                       "an encoding is chosen, and choosing one here would decide "
                       "the answer")
    return _against_bytes(record, bytes(data))


def _link_of(record: dict) -> str | None:
    """The record's own link, or None when it does not canonicalize."""
    try:
        return canonical_sha256(record)
    except (ValueError, TypeError):
        return None


def _resolved(resolve: Callable[[str], Any] | None, record: dict) -> tuple[Any, bool]:
    """(bytes or None, reachable). A resolver that throws is a resolver that failed."""
    if resolve is None:
        return None, False
    try:
        return resolve(record["sha256"]), True
    except Exception:  # a caller's storage is not this verifier's failure mode
        return None, False


def _chain_result(verdict: str, failure_class: str | None, broken_at: int | None,
                  head: str | None, checked: int, detail: str) -> dict:
    return {"schema": CHAIN_SCHEMA, "verdict": verdict,
            "failure_class": failure_class, "broken_at": broken_at,
            "head": head, "checked": checked, "detail": detail,
            "does_not_prove": does_not_prove() + [
                "the last record is checked by nothing after it, so bind the "
                "head somewhere a change to the chain cannot follow it"]}


def verify_chain(records: Any, *, start: str = GENESIS,
                 resolve: Callable[[str], Any] | None = None) -> dict:
    """Check that records form one chain, and their bytes when a resolver is given.

    ``start`` is what the first record must point back at. It defaults to
    genesis, so a segment lifted out of a longer chain is UNVERIFIABLE rather
    than quietly MATCH. A caller holding the earlier head passes it here.

    A broken link is TAMPERED, not UNVERIFIABLE. The words name the record, not
    an intent: whether a link broke through malice or through misassembly, the
    chain in hand does not hold, and it was checkable enough to say so.
    """
    if not isinstance(records, list) or not records:
        return _chain_result(UNVERIFIABLE, MALFORMED, None, None, 0,
                             "there is no chain here to check")
    if start != GENESIS and not _digest_well_formed(start):
        return _chain_result(UNVERIFIABLE, MALFORMED, None, None, 0,
                             "start is empty at genesis, or a 64-character link")
    expected, head, unresolved = start, None, 0
    for index, record in enumerate(records):
        one = verify_witness(record, _resolved(resolve, record)[0]
                             if isinstance(record, dict) and "sha256" in record else None)
        if one["verdict"] == TAMPERED:
            return _chain_result(TAMPERED, one["failure_class"], index, head,
                                 index, one["detail"])
        if one["failure_class"] == MALFORMED:
            return _chain_result(UNVERIFIABLE, MALFORMED, index, head, index,
                                 f"record {index}: {one['detail']}")
        if one["failure_class"] == BYTES_UNAVAILABLE:
            # The link is still checked below. A resolver was asked for
            # these bytes and could not produce them, so the chain is linked
            # but not fully reproduced, and MATCH would overstate what ran.
            unresolved += 1
        if record["prev"] != expected:
            return _chain_result(TAMPERED, LINK_BROKEN, index, head, index,
                                 f"record {index} points back at "
                                 f"{record['prev'] or 'genesis'}, and the record "
                                 f"before it links to {expected or 'genesis'}")
        head = _link_of(record)
        if head is None:
            return _chain_result(UNVERIFIABLE, MALFORMED, index, None, index,
                                 f"record {index} does not canonicalize, so it "
                                 "has no link")
        expected = head
    if resolve is None:
        return _chain_result(UNVERIFIABLE, BYTES_UNAVAILABLE, None, head, len(records),
                             f"{len(records)} records link into one chain; no "
                             "resolver was given, so no bytes were checked")
    if unresolved:
        return _chain_result(UNVERIFIABLE, BYTES_UNAVAILABLE, None, head, len(records),
                             f"{len(records)} records link into one chain; "
                             f"{unresolved} could not be resolved to bytes, so the "
                             "chain is linked but not fully reproduced")
    return _chain_result(MATCH, None, None, head, len(records),
                         f"{len(records)} records link into one chain and every "
                         "witnessed byte sequence reproduced")


def verify_signature(record: Any, signature_hex: Any, public_key_hex: Any) -> dict:
    """Check an Ed25519 signature over a record's link, on stdlib alone.

    The signed message is the link, as its lowercase hex text. Signing happens
    wherever the key lives. Nothing here ever holds one.
    """
    problem = _shape(record)
    if problem is not None:
        return _result(UNVERIFIABLE, MALFORMED, problem)
    if not signature_hex or not public_key_hex:
        return _result(UNVERIFIABLE, NO_SIGNER,
                       "the record carries no signature, so it is bound to no key")
    link = _link_of(record)
    if link is None:
        return _result(UNVERIFIABLE, MALFORMED, "the record does not canonicalize")
    try:
        signature = bytes.fromhex(str(signature_hex))
        public_key = bytes.fromhex(str(public_key_hex))
    except ValueError:
        return _result(UNVERIFIABLE, MALFORMED, "signature and key are hex")
    if len(signature) != 64 or len(public_key) != 32:
        return _result(UNVERIFIABLE, MALFORMED,
                       "an ed25519 signature is 64 bytes over a 32-byte key")
    from .ed25519_verify import Ed25519Error, verify as ed25519

    try:
        held = ed25519(public_key, link.encode("ascii"), signature)
    except (Ed25519Error, ValueError):
        return _result(UNVERIFIABLE, MALFORMED, "the key or signature is not on the curve")
    if not held:
        return _result(TAMPERED, SIGNATURE_INVALID,
                       "the signature does not verify over this record's link")
    return _result(MATCH, None, "the signature verifies over this record's link")
