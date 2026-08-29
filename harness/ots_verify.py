"""ots_verify.py -- check an OpenTimestamps proof to Bitcoin, stdlib only.

The external anchor's promise is that a stranger holding a bundle can confirm a
timestamp existed before a Bitcoin block, needing nothing but a Python that ships
with the standard library and the block header carried in the bundle. This module
is that check. It never trusts the recorded result of anything: it walks the
commitment operations from the digest we expected, and where the walk reaches a
Bitcoin attestation it rechecks the header's proof of work against a real target.
That recheck is internal consistency plus real work, not chain linkage: it
refuses a zero-work forgery, but a bundle-carried header is only as trustworthy
as its source (see `anchor.does_not_prove`).

The proof format is OpenTimestamps' detached-timestamp serialization: a magic
header, a version, the operation used to hash the file and that file's digest,
then a tree of operations and attestations. `\xff` forks the tree, `\x00`
introduces an attestation, any other tag is an operation whose sub-timestamp
continues from the transformed message. See the python-opentimestamps reference;
the byte-level rules are reproduced here rather than imported so the closure a
stranger runs stays standard-library-only.

This module raises nothing to its caller. Hostile bytes are the expected input,
so every failure is a named reason on the returned dict, not an exception.
"""
from __future__ import annotations

import binascii
import hashlib

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"

# 8-byte attestation tags from the OpenTimestamps registry.
BITCOIN_TAG = bytes.fromhex("0588960d73d71901")
PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")

# The op that hashed the file fixes the length of the digest that follows it.
# sha1 and ripemd160 are 20 bytes, sha256 is 32; reading a fixed 32 corrupts the
# first two and falsely rejects an otherwise valid non-sha256 proof.
_FILE_HASH_LEN = {0x02: 20, 0x03: 20, 0x08: 32}

# Bitcoin's maximum target (compact 0x1d00ffff). No mainnet block is mined with a
# target above this, so a header whose nBits decodes higher carries no work and
# must be refused. The genesis block's target equals it exactly, so the cap is
# inclusive.
POW_LIMIT = 0xFFFF << 208

# Guards against a proof that tries to exhaust memory rather than prove anything.
MAX_MSG = 4096
MAX_OPS = 4096
MAX_RESULT_LEN = 8192
# Attestations are not operations, so MAX_OPS does not bound them. A proof of
# thousands of empty attestation edges would otherwise grow the accumulator
# without limit; real proofs carry a handful.
MAX_ATTESTATIONS = 256
# Fork nesting only; a linear operation chain is walked iteratively and so is
# bounded by MAX_OPS, not by the interpreter's recursion limit. Real proofs fork
# a handful of levels deep; this is low enough that the guard trips well before
# Python's own recursion limit would, turning a hostile proof into a named reason.
MAX_DEPTH = 128


class OtsError(ValueError):
    """A proof that cannot be parsed as written. Never escapes `verify`."""


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def bytes(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise OtsError("truncated: ran off the end of the proof")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def varuint(self) -> int:
        result = shift = 0
        while True:
            b = self.bytes(1)[0]
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7
            if shift > 63:
                raise OtsError("varint too long")

    def varbytes(self) -> bytes:
        return self.bytes(self.varuint())


def _hash(name: str, msg: bytes) -> bytes:
    try:
        return hashlib.new(name, msg).digest()
    except (ValueError, TypeError) as e:  # e.g. ripemd160 absent from OpenSSL 3
        raise OtsError(f"{name} unavailable in this interpreter: {e}")


def _apply_op(tag: int, r: _Reader, msg: bytes) -> bytes:
    if tag == 0xF0:  # append
        msg = msg + r.varbytes()
    elif tag == 0xF1:  # prepend
        msg = r.varbytes() + msg
    elif tag == 0xF3:  # hexlify
        msg = binascii.hexlify(msg)
    elif tag == 0x02:
        msg = _hash("sha1", msg)
    elif tag == 0x03:
        msg = _hash("ripemd160", msg)
    elif tag == 0x08:
        msg = _hash("sha256", msg)
    else:
        raise OtsError(f"unsupported operation tag 0x{tag:02x}")
    if len(msg) > MAX_RESULT_LEN:
        raise OtsError("operation produced an oversize message")
    return msg


def _pow_ok(header: bytes) -> bool:
    """A header clears a real target: double-sha256, little-endian, <= target.

    Faithful to Bitcoin Core's CheckProofOfWork. The compact nBits must be a
    positive target (no sign bit), must not overflow, and must not exceed the
    network maximum; only then must the hash fall at or below it. Without the
    range checks this is a zero-work forgery: an nBits whose target is inflated
    past 2**256 is satisfied by any hash at all, so a fabricated header would
    verify against a digest that was never anchored.
    """
    if len(header) != 80:
        return False
    bits = int.from_bytes(header[72:76], "little")
    exponent, mantissa = bits >> 24, bits & 0x007FFFFF
    if mantissa and (bits & 0x00800000):  # a negative target: Bitcoin rejects it
        return False
    if exponent > 34:  # target would exceed 2**256; also bounds the shift below
        return False
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))
    if not 0 < target <= POW_LIMIT:  # above the network maximum is not real work
        return False
    digest = hashlib.sha256(hashlib.sha256(header).digest()).digest()
    value = int.from_bytes(digest, "little")
    return 0 < value <= target


def _check_bitcoin(height: int, msg: bytes, header_provider) -> dict:
    leaf = {"height": height, "reached": msg.hex(),
            "pow_ok": False, "merkle_ok": False, "verified": False,
            "reason": "unproven"}
    header = None
    if header_provider is not None:
        try:
            header = header_provider(height)
        except Exception as e:  # a provider is caller code; do not let it escape
            leaf["reason"] = f"header_provider_error: {e}"
            return leaf
    if not header:
        leaf["reason"] = f"header_unavailable: no header supplied for height {height}"
        return leaf
    if len(header) != 80:
        leaf["reason"] = "header_unavailable: header is not 80 bytes"
        return leaf
    leaf["pow_ok"] = _pow_ok(header)
    leaf["merkle_ok"] = (header[36:68] == msg)
    if not leaf["pow_ok"]:
        leaf["reason"] = "proof_of_work_failed"
    elif not leaf["merkle_ok"]:
        leaf["reason"] = "message_is_not_this_block_merkle_root"
    else:
        leaf["verified"] = True
        leaf["reason"] = "ok"
    return leaf


def _record_attestation(r: _Reader, msg: bytes, acc: dict) -> None:
    """Read one `0x00` attestation edge and file it under its kind."""
    acc["_atts"] += 1
    if acc["_atts"] > MAX_ATTESTATIONS:
        raise OtsError("too many attestations")
    att_tag = r.bytes(8)
    payload = r.varbytes()
    sub = _Reader(payload)
    if att_tag == BITCOIN_TAG:
        acc["bitcoin"].append(_check_bitcoin(sub.varuint(), msg, acc["_provider"]))
    elif att_tag == PENDING_TAG:
        acc["pending"].append({"uri": sub.varbytes().decode("utf-8", "replace"),
                               "reached": msg.hex()})
    else:
        acc["unknown"].append({"tag": att_tag.hex(), "reached": msg.hex()})


def _count_op(budget: list) -> None:
    budget[0] += 1
    if budget[0] > MAX_OPS:
        raise OtsError("too many operations")


def _edge(r: _Reader, msg: bytes, acc: dict, budget: list, depth: int) -> None:
    """One forked (`0xff`-introduced) edge: an attestation, or an operation whose
    sub-timestamp is a fresh branch. Only the branch recurses, guarded by depth."""
    tag = r.bytes(1)[0]
    if tag == 0x00:
        _record_attestation(r, msg, acc)
        return
    _count_op(budget)
    _walk(r, _apply_op(tag, r, msg), acc, budget, depth + 1)


def _walk(r: _Reader, msg: bytes, acc: dict, budget: list, depth: int = 0) -> None:
    """Walk one timestamp to its attestations, collecting them into `acc`.

    A linear operation chain continues this same timestamp and is followed by the
    loop, so a proof of thousands of sequential ops costs no stack. Only a forked
    edge starts a new branch, and that recursion is bounded by MAX_DEPTH, so a
    crafted proof cannot exhaust the interpreter stack instead of proving a time.
    """
    if depth > MAX_DEPTH:
        raise OtsError("timestamp tree nested too deeply")
    while True:
        if len(msg) > MAX_MSG:
            raise OtsError("message exceeded the size guard")
        tag = r.bytes(1)[0]
        while tag == 0xFF:  # forked edges: each is a complete sub-timestamp
            _edge(r, msg, acc, budget, depth)
            tag = r.bytes(1)[0]
        if tag == 0x00:  # the final edge is an attestation: this timestamp ends
            _record_attestation(r, msg, acc)
            return
        _count_op(budget)  # the final edge is an operation: continue by looping
        msg = _apply_op(tag, r, msg)


def verify(ots_bytes: bytes, expected_digest: bytes, header_provider=None) -> dict:
    """Verify an OTS detached proof; return a result dict, never raise.

    `expected_digest`: the 32 bytes the proof must start from (the anchor digest).
    `header_provider`: callable(height:int) -> 80-byte header or None. Without it,
    Bitcoin attestations are reported present but unproven, which is honest.
    `ok` is True only when the digest binds and at least one Bitcoin attestation
    verifies against a proof-of-work-checked header.
    """
    acc = {"ok": False, "reason": "", "file_digest": None, "_atts": 0,
           "bitcoin": [], "pending": [], "unknown": [], "_provider": header_provider}
    try:
        r = _Reader(bytes(ots_bytes))
        if r.bytes(len(MAGIC)) != MAGIC:
            acc["reason"] = "malformed: not an OpenTimestamps proof"
            return _finish(acc)
        r.varuint()  # major version; forward-compatible, not pinned here
        hash_op = r.bytes(1)[0]  # the file-hash op fixes the digest length
        if hash_op not in _FILE_HASH_LEN:
            acc["reason"] = f"malformed: unsupported file-hash op 0x{hash_op:02x}"
            return _finish(acc)
        file_digest = r.bytes(_FILE_HASH_LEN[hash_op])
        acc["file_digest"] = file_digest.hex()
        if file_digest != bytes(expected_digest):
            acc["reason"] = "digest_mismatch: proof does not cover this artifact"
            return _finish(acc)
        _walk(r, file_digest, acc, [0])
    except OtsError as e:
        acc["reason"] = f"malformed: {e}"
        return _finish(acc)
    return _finish(acc)


def _finish(acc: dict) -> dict:
    acc.pop("_provider", None)
    acc.pop("_atts", None)
    if not acc["reason"]:
        if any(b["verified"] for b in acc["bitcoin"]):
            acc["ok"], acc["reason"] = True, "ok"
        elif acc["bitcoin"]:
            acc["reason"] = acc["bitcoin"][0]["reason"]
        elif acc["pending"]:
            acc["reason"] = "pending: submitted to a calendar, not yet in a block"
        elif acc["unknown"]:
            tags = ", ".join(sorted({u["tag"] for u in acc["unknown"]}))
            acc["reason"] = f"unverifiable_attestation: present but not checkable here ({tags})"
        else:
            acc["reason"] = "no_attestation"
    return acc
