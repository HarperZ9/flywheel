"""Assembling a .ots from a calendar reply, checked by our own verifier offline.

The network leg is not exercised here; `build_ots` is the pure part, and the test
proves the proof it builds is one `ots_verify` accepts, with the privacy nonce
walked correctly before the calendar's own commitment.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import anchor_submit  # noqa: E402
from harness import ots_verify  # noqa: E402

PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")


def _varuint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _varbytes(b):
    return _varuint(len(b)) + b


def test_build_ots_wraps_a_calendar_reply_into_a_verifiable_pending_proof():
    digest = hashlib.sha256(b"artifact").digest()
    nonce = b"\xaa" * 16
    uri = "https://alice.calendar.example/x"
    # A calendar's reply: from the submitted digest straight to a pending leaf.
    calendar_reply = b"\x00" + PENDING_TAG + _varbytes(_varbytes(uri.encode()))
    ots = anchor_submit.build_ots(digest, nonce, calendar_reply)

    r = ots_verify.verify(ots, digest)
    assert r["file_digest"] == digest.hex()
    assert r["pending"][0]["uri"] == uri
    # the nonce is appended then sha256'd, so the calendar commits the SUBMITTED
    # digest, never the artifact digest.
    submitted = hashlib.sha256(digest + nonce).hexdigest()
    assert r["pending"][0]["reached"] == submitted


def test_submitted_digest_is_the_nonced_hash_not_the_artifact():
    digest = hashlib.sha256(b"artifact").digest()
    nonce = b"\x01" * 16
    assert anchor_submit.submitted_digest(digest, nonce) == hashlib.sha256(
        digest + nonce).digest()


def test_a_nonce_is_16_random_bytes_and_differs_each_call():
    a, b = anchor_submit.fresh_nonce(), anchor_submit.fresh_nonce()
    assert len(a) == 16 and len(b) == 16
    assert a != b  # secrets, not a constant
