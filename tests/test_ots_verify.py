"""A stranger holding a bundle checks a Bitcoin timestamp with only the stdlib.

The vectors are built here, so nothing about the proof format is taken on trust
from the module under test. The Bitcoin leaf uses the real genesis block: its
80-byte header and merkle root are fixed history, so `pow_ok` and `merkle_ok` are
checkable facts rather than fixtures a test could fake.
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import ots_verify as ots  # noqa: E402

# The genesis block, byte-for-byte. header[36:68] is its merkle root.
GENESIS_HEADER = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
GENESIS_MERKLE = GENESIS_HEADER[36:68]

BITCOIN_TAG = bytes.fromhex("0588960d73d71901")
PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")
MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"


def _varuint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _varbytes(b):
    return _varuint(len(b)) + b


def _raw_bitcoin(height):
    return BITCOIN_TAG + _varbytes(_varuint(height))


def _raw_pending(uri):
    return PENDING_TAG + _varbytes(_varbytes(uri.encode()))


def _ots(file_digest, body):
    return MAGIC + b"\x01" + b"\x08" + file_digest + body


def _genesis_leaf():
    # file digest IS the merkle root, zero ops, one Bitcoin attestation.
    return _ots(GENESIS_MERKLE, b"\x00" + _raw_bitcoin(0))


def _provider(header):
    return lambda height: header


def test_a_bitcoin_leaf_verifies_against_a_pow_checked_header():
    r = ots.verify(_genesis_leaf(), GENESIS_MERKLE, _provider(GENESIS_HEADER))
    assert r["ok"] is True
    leaf = r["bitcoin"][0]
    assert leaf["height"] == 0
    assert leaf["pow_ok"] is True
    assert leaf["merkle_ok"] is True
    assert leaf["verified"] is True


def test_ops_are_walked_in_order_before_the_attestation():
    d = hashlib.sha256(b"hello").digest()
    # append 0x00, then sha256, then a pending calendar.
    body = b"\xf0" + _varbytes(b"\x00") + b"\x08" + b"\x00" + _raw_pending(
        "https://a.calendar.example/digest")
    r = ots.verify(_ots(d, body), d)
    assert r["ok"] is False  # pending is not yet anchored
    assert r["bitcoin"] == []
    reached = r["pending"][0]["reached"]
    assert reached == hashlib.sha256(d + b"\x00").hexdigest()


def test_a_fork_captures_every_pending_calendar():
    d = b"\x22" * 32
    body = (b"\xff\x00" + _raw_pending("https://one.example/digest")
            + b"\x00" + _raw_pending("https://two.example/digest"))
    r = ots.verify(_ots(d, body), d)
    uris = sorted(p["uri"] for p in r["pending"])
    assert uris == ["https://one.example/digest", "https://two.example/digest"]


def test_a_tampered_header_fails_proof_of_work():
    bad = bytearray(GENESIS_HEADER)
    bad[79] ^= 0x01  # flip a nonce bit; the hash no longer clears the target
    r = ots.verify(_genesis_leaf(), GENESIS_MERKLE, _provider(bytes(bad)))
    leaf = r["bitcoin"][0]
    assert leaf["pow_ok"] is False
    assert leaf["verified"] is False
    assert r["ok"] is False


def test_a_merkle_root_that_does_not_match_the_message_is_refused():
    digest = b"\x11" * 32  # a valid-PoW header, but not this message's root
    r = ots.verify(_ots(digest, b"\x00" + _raw_bitcoin(0)), digest,
                   _provider(GENESIS_HEADER))
    leaf = r["bitcoin"][0]
    assert leaf["pow_ok"] is True
    assert leaf["merkle_ok"] is False
    assert leaf["verified"] is False
    assert r["ok"] is False


def test_the_proof_must_start_from_the_digest_we_expected():
    r = ots.verify(_genesis_leaf(), b"\x99" * 32, _provider(GENESIS_HEADER))
    assert r["ok"] is False
    assert "digest" in r["reason"]


def test_a_bitcoin_leaf_with_no_header_available_is_unproven_not_crashing():
    r = ots.verify(_genesis_leaf(), GENESIS_MERKLE, lambda h: None)
    leaf = r["bitcoin"][0]
    assert leaf["verified"] is False
    assert "header_unavailable" in leaf["reason"]
    assert r["ok"] is False


def test_a_wrong_magic_is_a_named_refusal_not_an_exception():
    r = ots.verify(b"this is not an ots proof", b"\x00" * 32)
    assert r["ok"] is False
    assert "malformed" in r["reason"]


def test_a_truncated_proof_never_raises():
    r = ots.verify(_genesis_leaf()[:25], GENESIS_MERKLE, _provider(GENESIS_HEADER))
    assert r["ok"] is False
    assert "malformed" in r["reason"]


def test_a_long_linear_operation_chain_is_refused_not_a_stack_overflow():
    # A hostile proof: thousands of sha256 ops in a line. The walk must not
    # recurse per op, or Python's own recursion limit turns a malformed proof
    # into an uncaught RecursionError. It stays a named reason on the dict.
    digest = hashlib.sha256(b"x").digest()
    body = b"\x08" * 3000  # sha256 op takes no argument; a linear chain
    r = ots.verify(_ots(digest, body), digest)
    assert r["ok"] is False
    assert "malformed" in r["reason"]


def test_a_deeply_nested_fork_chain_is_refused_not_a_stack_overflow():
    # Each op-edge's sub-timestamp is itself a fork, nesting the walk. Depth is
    # guarded so a crafted proof cannot exhaust the stack; the refusal is named.
    digest = hashlib.sha256(b"y").digest()
    # 0xff introduces a forked edge; 0x08 is an op whose sub-timestamp follows.
    body = (b"\xff\x08") * 3000 + b"\x00" + _raw_pending("https://x")
    r = ots.verify(_ots(digest, body), digest)
    assert r["ok"] is False
    assert "malformed" in r["reason"]
