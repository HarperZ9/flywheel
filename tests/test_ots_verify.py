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
LITECOIN_TAG = bytes.fromhex("06869a0d73d71b45")
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


def _forged_header(merkle32, nbits_le):
    """An 80-byte header an attacker controls: version, zero prev, chosen merkle
    field, zero time, chosen nBits (little-endian), zero nonce."""
    return (b"\x01\x00\x00\x00" + b"\x00" * 32 + merkle32
            + b"\x00\x00\x00\x00" + nbits_le + b"\x00\x00\x00\x00")


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


def test_an_oversize_exponent_target_is_not_a_zero_work_pass():
    # The zero-work forgery: a digest that was never anchored, wearing a header
    # whose nBits exponent inflates the target past 2**256 so ANY hash clears it.
    # Bitcoin never mines above the network maximum; a header claiming to must be
    # refused, or the proof-of-work check proves nothing.
    forged = bytes.fromhex("de" * 32)
    header = _forged_header(forged, bytes.fromhex("ffff7f21"))  # nBits 0x217fffff
    assert ots._pow_ok(header) is False
    r = ots.verify(_ots(forged, b"\x00" + _raw_bitcoin(0)), forged,
                   _provider(header))
    assert r["ok"] is False
    assert r["bitcoin"][0]["pow_ok"] is False
    assert "proof_of_work" in r["bitcoin"][0]["reason"]


def test_a_target_above_the_network_maximum_is_refused():
    # nBits 0x2100ffff decodes to a target far above the mainnet powLimit but
    # still inside a plausible exponent range, so the exponent-size guard alone
    # would miss it. The powLimit cap is what refuses it.
    forged = bytes.fromhex("ab" * 32)
    header = _forged_header(forged, bytes.fromhex("ffff0021"))  # nBits 0x2100ffff
    assert ots._pow_ok(header) is False
    r = ots.verify(_ots(forged, b"\x00" + _raw_bitcoin(0)), forged,
                   _provider(header))
    assert r["ok"] is False
    assert r["bitcoin"][0]["pow_ok"] is False


def test_the_genesis_block_still_verifies_at_the_powlimit_boundary():
    # The cap is inclusive: the genesis block's target equals powLimit exactly,
    # so a correct fix must still admit it. Guards the cap against off-by-one.
    assert ots._pow_ok(GENESIS_HEADER) is True
    r = ots.verify(_genesis_leaf(), GENESIS_MERKLE, _provider(GENESIS_HEADER))
    assert r["ok"] is True


def test_a_flood_of_attestations_is_refused_not_accumulated_without_bound():
    # Attestations are recorded but never counted against MAX_OPS, so a proof of
    # thousands of empty attestation edges grows the accumulator without limit.
    # The walk must refuse the flood with a named reason.
    d = b"\x33" * 32
    edge = b"\xff\x00" + b"\x22" * 8 + b"\x00"  # fork -> unknown 8-byte tag, empty
    body = edge * 400 + b"\x00" + b"\x22" * 8 + b"\x00"
    r = ots.verify(_ots(d, body), d)
    assert r["ok"] is False
    assert "malformed" in r["reason"]


def test_a_sha1_file_hash_proof_is_parsed_at_its_true_length():
    # A proof whose file-hash op is SHA1 carries a 20-byte digest, not 32. Reading
    # a fixed 32 bytes swallows the first bytes of the tree and falsely rejects a
    # correct proof. The op tag dictates the length.
    sha1d = hashlib.sha1(b"hello").digest()
    proof = (MAGIC + b"\x01" + b"\x02" + sha1d
             + b"\x00" + _raw_pending("https://one.example/digest"))
    r = ots.verify(proof, sha1d)
    assert r["file_digest"] == sha1d.hex()
    assert r["pending"] and "pending" in r["reason"]


def test_an_unverifiable_attestation_is_named_not_reported_absent():
    # A Litecoin (or any unregistered) attestation is present but this verifier
    # cannot check it. Reporting "no_attestation" is a lie: an attestation IS
    # there, it is simply unverifiable here. The reason must say so.
    d = b"\x44" * 32
    r = ots.verify(_ots(d, b"\x00" + LITECOIN_TAG + _varbytes(_varuint(999))), d)
    assert r["ok"] is False
    assert r["unknown"]
    assert "unverifiable" in r["reason"]


def test_non_bytes_proof_or_digest_is_a_named_refusal_not_an_exception():
    # bytes(ots_bytes) and bytes(expected_digest) run inside a try that catches
    # only OtsError; a str/None argument raises TypeError, which the module's
    # "raises nothing to its caller" contract must not let escape. A stranger who
    # opened the proof in text mode, or passed a hex string, gets a verdict.
    r = ots.verify("not-bytes", b"\x00" * 32)
    assert r["ok"] is False
    assert "malformed" in r["reason"]
    r2 = ots.verify(_genesis_leaf(), None)
    assert r2["ok"] is False
    assert "malformed" in r2["reason"]


def test_a_header_provider_returning_a_non_bytes_value_is_unproven_not_crashing():
    # A provider that returns a length-80 str or list (a header file opened in text
    # mode, a hex string) passes the truthy and length gates but is not bytes.
    # _pow_ok would then TypeError inside int.from_bytes; the module must turn a
    # bad provider return into a named header_unavailable, not an escaping crash.
    for bad in ("x" * 80, [0] * 80, [7] * 80):
        r = ots.verify(_genesis_leaf(), GENESIS_MERKLE, lambda h, v=bad: v)
        leaf = r["bitcoin"][0]
        assert leaf["verified"] is False
        assert "header_unavailable" in leaf["reason"]
        assert r["ok"] is False


def test_a_hexlify_chain_that_doubles_the_message_hits_the_size_guard():
    # Each 0xf3 hexlify op doubles the message (32->64->...); MAX_OPS never trips,
    # so the MAX_MSG guard in _walk is the only thing between a stranger's verifier
    # and a 32*2**30-byte OOM. Drive the message past it and assert the named
    # refusal, so a refactor that loosens that guard fails here.
    d = hashlib.sha256(b"z").digest()
    body = b"\xf3" * 30 + b"\x00" + _raw_pending("https://x")
    r = ots.verify(_ots(d, body), d)
    assert r["ok"] is False
    assert "size guard" in r["reason"]


def test_a_header_provider_that_raises_is_a_named_reason_not_an_escaping_crash():
    # header_provider is the one place caller code runs inside verify. A provider
    # that raises must become a header_provider_error leaf, never an exception out
    # of verify -- the module's "raises nothing to its caller" contract.
    r = ots.verify(_genesis_leaf(), GENESIS_MERKLE, lambda h: 1 / 0)
    leaf = r["bitcoin"][0]
    assert leaf["verified"] is False
    assert "header_provider_error" in leaf["reason"]
    assert r["ok"] is False


def test_an_overlong_varuint_in_the_verifier_is_a_named_refusal():
    # verify reads a varuint for the major version straight after MAGIC, on
    # attacker bytes. A run of 0x80 continuation bytes would build an ever-wider
    # integer without the shift>63 guard; assert the named refusal instead.
    r = ots.verify(MAGIC + b"\x80" * 10, b"\x00" * 32)
    assert r["ok"] is False
    assert "varint too long" in r["reason"]
