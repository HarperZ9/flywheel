"""Assembling a .ots from a calendar reply, checked by our own verifier offline.

The network leg is not exercised here; `build_ots` is the pure part, and the test
proves the proof it builds is one `ots_verify` accepts, with the privacy nonce
walked correctly before the calendar's own commitment.
"""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import anchor_submit  # noqa: E402
from harness import ots_verify  # noqa: E402

PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")
BITCOIN_TAG = bytes.fromhex("0588960d73d71901")
MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"

# The genesis block, byte-for-byte: real history, so pow_ok/merkle_ok are facts,
# not fixtures. header[36:68] is its merkle root.
GENESIS_HEADER = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_MERKLE = GENESIS_HEADER[36:68]


def _varuint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _varbytes(b):
    return _varuint(len(b)) + b


def _pending_on(message, uri="https://alice.calendar.example"):
    """A hand-built pending proof whose pending attestation sits directly on
    `message` (zero calendar ops), so the message the calendar keys its upgrade on
    is exactly `message`."""
    body = b"\x00" + PENDING_TAG + _varbytes(_varbytes(uri.encode()))
    return MAGIC + b"\x01" + b"\x08" + message + body


def _bitcoin_edge(height):
    """A calendar continuation that is nothing but a Bitcoin attestation."""
    return b"\x00" + BITCOIN_TAG + _varbytes(_varuint(height))


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


# --- the upgrade path: poll the pending message R, splice, not rebuild -------
#
# A calendar folds the submitted digest into its aggregation tree and puts the
# pending attestation on the tree message R, not on the submitted digest. The
# Bitcoin upgrade is keyed on R. Polling the submitted digest 404s forever even
# after the block lands; the fix polls R (the `reached` value) and SPLICES the
# continuation onto the pending proof, preserving the ops that reach R.

def test_pending_target_reports_the_message_the_calendar_keys_its_upgrade_on():
    # build_ots appends the nonce then sha256, so the pending message is the
    # SUBMITTED digest sha256(artifact+nonce), NOT the artifact digest. Polling
    # anything else is the bug this guards against.
    digest = hashlib.sha256(b"artifact").digest()
    nonce = b"\xaa" * 16
    reply = b"\x00" + PENDING_TAG + _varbytes(_varbytes(b"https://c.example"))
    ots = anchor_submit.build_ots(digest, nonce, reply)

    target = anchor_submit.pending_target(ots, digest)
    assert target is not None
    r, uri = target
    assert r == hashlib.sha256(digest + nonce).digest()
    assert uri == "https://c.example"


def test_pending_target_is_none_when_there_is_no_pending_attestation():
    # a confirmed (or digest-mismatched) proof has nothing to upgrade
    assert anchor_submit.pending_target(_pending_on(GENESIS_MERKLE),
                                        b"\x00" * 32) is None


def test_splice_upgrade_replaces_the_pending_leaf_with_the_block_continuation():
    # pending on the genesis merkle root; the continuation is the genesis block's
    # own Bitcoin attestation. The spliced proof must verify against a real
    # PoW-checked header, proving the ops that reach the pending message survive.
    pending = _pending_on(GENESIS_MERKLE)
    spliced = anchor_submit.splice_upgrade(pending, _bitcoin_edge(0))

    checked = ots_verify.verify(spliced, GENESIS_MERKLE, lambda h: GENESIS_HEADER)
    assert checked["ok"] is True
    assert checked["bitcoin"][0]["height"] == 0
    assert checked["bitcoin"][0]["verified"] is True
    assert checked["pending"] == []          # the promise is gone, the block is in


def test_splice_upgrade_refuses_a_proof_with_no_terminal_pending_edge():
    # a proof already ending in a Bitcoin attestation has no pending edge to
    # splice onto; refuse rather than corrupt the bytes
    confirmed = MAGIC + b"\x01" + b"\x08" + GENESIS_MERKLE + _bitcoin_edge(0)
    with pytest.raises(anchor_submit.SubmitError):
        anchor_submit.splice_upgrade(confirmed, _bitcoin_edge(0))


def test_upgrade_proof_polls_R_not_the_submitted_digest_and_splices():
    # the injected get records exactly what hex the upgrade queries. R here equals
    # the file digest (zero ops), so the query must be R, and the returned proof
    # must carry the block.
    pending = _pending_on(GENESIS_MERKLE)
    seen = {}

    def get(uri, r_hex):
        seen["uri"], seen["r_hex"] = uri, r_hex
        return _bitcoin_edge(0)

    full = anchor_submit.upgrade_proof(pending, GENESIS_MERKLE, get=get,
                                       fetch_header=lambda h: GENESIS_HEADER)
    assert seen["r_hex"] == GENESIS_MERKLE.hex()
    assert seen["uri"] == "https://alice.calendar.example"
    checked = ots_verify.verify(full, GENESIS_MERKLE, lambda h: GENESIS_HEADER)
    assert checked["ok"] is True


def test_upgrade_proof_returns_none_while_the_calendar_is_still_pending():
    pending = _pending_on(GENESIS_MERKLE)
    full = anchor_submit.upgrade_proof(pending, GENESIS_MERKLE,
                                       get=lambda uri, r_hex: None)
    assert full is None


def test_block_header_returns_the_injected_80_byte_header():
    assert anchor_submit.block_header(0, fetch=lambda h: GENESIS_HEADER) == GENESIS_HEADER


def test_block_header_refuses_a_reply_that_is_not_80_bytes():
    with pytest.raises(anchor_submit.SubmitError):
        anchor_submit.block_header(0, fetch=lambda h: b"\x00" * 79)


# --- hardening the upgrade path: the invariants the splice depends on --------
#
# The confirmed anchor was built through the single-calendar path, where the
# pending message equals the submitted digest and exactly one calendar answered.
# These guard the paths a multi-calendar upgrade, a flaky calendar, or a garbage
# reply would take -- none of which the single-calendar happy path exercises.

def _pending_after_append_sha256(digest, extra, uri="https://alice.calendar.example"):
    """A pending proof whose message R is `sha256(digest + extra)`, reached by an
    append then a sha256 -- the shape a real calendar's aggregation tree produces,
    where the pending attestation sits on R, not on the artifact digest."""
    ops = b"\xf0" + _varbytes(extra) + b"\x08"
    body = b"\x00" + PENDING_TAG + _varbytes(_varbytes(uri.encode()))
    return MAGIC + b"\x01" + b"\x08" + digest + ops + body


def _two_pending(message, uri_a="https://a.example", uri_b="https://b.example"):
    """A proof carrying two pending attestations on `message` (a fork), the shape a
    submission to more than one calendar produces."""
    a = b"\x00" + PENDING_TAG + _varbytes(_varbytes(uri_a.encode()))
    b = b"\x00" + PENDING_TAG + _varbytes(_varbytes(uri_b.encode()))
    return MAGIC + b"\x01" + b"\x08" + message + b"\xff" + a + b


def test_upgrade_proof_preserves_aggregation_ops_when_R_differs_from_the_digest():
    # Every other fixture here is zero-op (R == the digest). A real calendar folds
    # the submitted digest into an aggregation tree, so R = sha256(digest + tree
    # bytes) != the digest. The upgrade must poll R and splice the block onto the
    # END of those ops; rebuilding from the digest would drop them and the proof
    # would not verify. This guards the exact R != digest invariant the splice is for.
    digest = hashlib.sha256(b"artifact").digest()
    extra = b"\x11" * 8
    R = hashlib.sha256(digest + extra).digest()
    assert R != digest
    pending = _pending_after_append_sha256(digest, extra)

    assert anchor_submit.pending_target(pending, digest)[0] == R  # polls R, not D

    seen = {}

    def get(uri, r_hex):
        seen["r_hex"] = r_hex
        return _bitcoin_edge(0)

    # The fabricated block sits directly on R, and no real header has merkle root R
    # (that needs a sha256 preimage), so the strengthened re-verify refuses it. The
    # poll still happened on R, which is the R != digest invariant under test.
    with pytest.raises(anchor_submit.SubmitError):
        anchor_submit.upgrade_proof(pending, digest, get=get,
                                    fetch_header=lambda h: GENESIS_HEADER)
    assert seen["r_hex"] == R.hex()  # polled R, not the digest
    # the append+sha256 ops survive the splice structurally: the block is reached
    # THROUGH them, so the bitcoin leaf sits on R, not on the artifact digest. This
    # is the splice_upgrade layer; full proof-of-work verify needs a real header
    # whose merkle root equals R, which is not constructible without a preimage.
    spliced = anchor_submit.splice_upgrade(pending, _bitcoin_edge(0))
    checked = ots_verify.verify(spliced, digest)
    assert checked["file_digest"] == digest.hex()
    assert checked["bitcoin"][0]["reached"] == R.hex()


def test_upgrade_proof_refuses_a_proof_carrying_more_than_one_pending_attestation():
    # `pending_target` reads the FIRST pending; `splice_upgrade` replaces the LAST.
    # On a multi-calendar proof those are different branches, so the splice would
    # graft one calendar's block onto another calendar's promise -- an unverifiable
    # proof. Refuse at the source rather than emit it. (The tool's own submit() only
    # ever produces a single-pending proof; this hardens the multi-calendar path.)
    pending = _two_pending(GENESIS_MERKLE)
    assert len(ots_verify.verify(pending, GENESIS_MERKLE)["pending"]) == 2

    def get(uri, r_hex):
        raise AssertionError("must not poll a calendar for an ambiguous proof")

    with pytest.raises(anchor_submit.SubmitError):
        anchor_submit.upgrade_proof(pending, GENESIS_MERKLE, get=get)


def test_upgrade_proof_refuses_a_continuation_that_does_not_reach_a_block():
    # A calendar can answer 200 with bytes that do not walk to a Bitcoin
    # attestation (an error page, a bug). Splicing them destroys the only pending
    # proof and yields something that verifies to nothing. upgrade_proof must
    # re-verify the splice and refuse, leaving the good pending proof for the caller.
    pending = _pending_on(GENESIS_MERKLE)
    with pytest.raises(anchor_submit.SubmitError):
        anchor_submit.upgrade_proof(pending, GENESIS_MERKLE,
                                    get=lambda uri, r_hex: b"not-a-real-continuation")


def test_upgrade_proof_refuses_a_continuation_whose_block_header_fails_pow():
    # The re-verify must check the block, not just that a Bitcoin edge parsed.
    # Header-less, verify() records the leaf present-but-unproven, so a forged
    # continuation carrying a fabricated Bitcoin attestation would clear a mere
    # non-emptiness check and overwrite the good pending proof. A flipped nonce bit
    # makes the PoW recheck fail; upgrade_proof must refuse and keep the pending
    # proof rather than emit one that verifies to nothing.
    pending = _pending_on(GENESIS_MERKLE)
    tampered = bytearray(GENESIS_HEADER)
    tampered[79] ^= 0x01
    with pytest.raises(anchor_submit.SubmitError):
        anchor_submit.upgrade_proof(
            pending, GENESIS_MERKLE,
            get=lambda uri, r_hex: _bitcoin_edge(0),
            fetch_header=lambda h: bytes(tampered))


def test_splice_upgrade_refuses_a_truncated_pending_length():
    # a pending marker whose length varuint never terminates (a lone 0x80 at the
    # end): the reader runs off the buffer. That is a SubmitError, not a raw crash.
    truncated = (MAGIC + b"\x01" + b"\x08" + GENESIS_MERKLE
                 + b"\x00" + PENDING_TAG + b"\x80")
    with pytest.raises(anchor_submit.SubmitError):
        anchor_submit.splice_upgrade(truncated, _bitcoin_edge(0))


def test_read_varuint_refuses_an_overlong_encoding():
    # ten continuation bytes cannot encode a 64-bit varuint; without a shift guard
    # the reader silently accepts it as 0. Refuse it, matching the verifier's guard.
    with pytest.raises(anchor_submit.SubmitError):
        anchor_submit._read_varuint(b"\x80" * 10 + b"\x00", 0)
