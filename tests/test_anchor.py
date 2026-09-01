"""The anchor binds a signed tree head to a timestamp over one digest.

A stranger recomputes that digest from the signed head they hold and checks the
OpenTimestamps proof starts from it. These tests use a real Ed25519 key so the
signed head is genuinely checkable, and drive the timestamp leg with a pending
proof (a Bitcoin leaf would need a forged block, which is the point of the anchor).
"""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import anchor  # noqa: E402
from harness import tree_head  # noqa: E402
from harness.receipt_fields import canonical  # noqa: E402

cryptography = pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey)

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
PENDING_TAG = bytes.fromhex("83dfe30d2ef90c8e")
HEAD = {"size": 7, "root": "sha256:" + "a" * 64}
TS = "2026-08-27T00:00:00Z"


def _key():
    sk = Ed25519PrivateKey.generate()
    return sk, (lambda b: sk.sign(b)), sk.public_key().public_bytes_raw()


def _varuint(n):
    out = bytearray()
    while True:
        b, n = n & 0x7F, n >> 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def _pending_proof(digest: bytes, uri: str) -> bytes:
    payload = _varuint(len(uri.encode())) + uri.encode()
    att = b"\x00" + PENDING_TAG + _varuint(len(payload)) + payload
    return MAGIC + b"\x01" + b"\x08" + digest + att


def test_the_anchor_digest_is_sha256_over_the_canonical_signed_head():
    _, sign, pub = _key()
    signed = tree_head.sign_head(HEAD, sign, public_key=pub, timestamp=TS)
    a = anchor.build_anchor(signed)
    expected = hashlib.sha256(canonical(signed).encode()).hexdigest()
    assert a["anchor_digest"] == "sha256:" + expected
    assert a["digest_hex"] == expected


def test_sign_and_anchor_produces_a_head_a_stranger_can_check():
    _, sign, pub = _key()
    a = anchor.sign_and_anchor(HEAD, sign, public_key=pub, timestamp=TS)
    ok, reason = tree_head.check_signed_head(a["signed_head"], pub)
    assert (ok, reason) == (True, "ok")


def test_verify_anchor_ties_the_head_to_a_timestamp_over_its_digest():
    _, sign, pub = _key()
    a = anchor.sign_and_anchor(HEAD, sign, public_key=pub, timestamp=TS)
    proof = _pending_proof(bytes.fromhex(a["digest_hex"]), "https://cal.example/x")
    r = anchor.verify_anchor(a, pub, ots_bytes=proof)
    assert r["head_ok"] is True
    assert r["timestamp"]["file_digest"] == a["digest_hex"]
    assert "pending" in r["timestamp"]["reason"]


def test_verify_anchor_catches_a_timestamp_over_a_different_digest():
    _, sign, pub = _key()
    a = anchor.sign_and_anchor(HEAD, sign, public_key=pub, timestamp=TS)
    proof = _pending_proof(b"\x00" * 32, "https://cal.example/x")  # wrong digest
    r = anchor.verify_anchor(a, pub, ots_bytes=proof)
    assert r["ok"] is False
    assert "digest_mismatch" in r["timestamp"]["reason"]


def test_verify_anchor_without_a_proof_reports_head_only_honestly():
    _, sign, pub = _key()
    a = anchor.sign_and_anchor(HEAD, sign, public_key=pub, timestamp=TS)
    r = anchor.verify_anchor(a, pub)
    assert r["head_ok"] is True
    assert r["timestamp"] == "absent"
    assert r["ok"] is False  # a head with no timestamp is not anchored


def test_verify_anchor_rejects_a_head_signed_by_another_key():
    _, sign, _ = _key()
    _, _, other_pub = _key()
    a = anchor.sign_and_anchor(HEAD, sign, public_key=other_pub, timestamp=TS)
    # signed with key A's callable but claiming key B; the signature will not check
    r = anchor.verify_anchor(a, other_pub)
    assert r["head_ok"] is False


def test_verify_anchor_names_a_non_finite_float_head_instead_of_crashing():
    # json.loads accepts NaN/Infinity/-Infinity by default, but canonical() forbids
    # them (allow_nan=False). A stranger running verify on an attacker record whose
    # signed_head carries one must get a named reason, not a ValueError escaping the
    # verifier the module docstring promises "raises nothing".
    import json
    for bad in ('{"signed_head": {"size": NaN}}',
                '{"signed_head": {"size": Infinity}}',
                '{"signed_head": {"size": -Infinity}}'):
        rec = json.loads(bad)
        r = anchor.verify_anchor(rec, b"\x00" * 32)
        assert r["ok"] is False
        assert "malformed_anchor" in r["head_reason"]


def test_verify_anchor_returns_a_verdict_on_a_deeply_nested_head():
    # A stranger runs verify on an attacker record whose signed_head is nested
    # deep. canonical() inside anchor_digest can raise RecursionError, which the
    # `except (ValueError, RecursionError)` guarding that call turns into a named
    # drift verdict rather than an escape -- the "raises nothing" contract the NaN
    # case honours one branch over. Whether json.dumps trips at a given depth is a
    # property of the interpreter's C stack and differs by platform and build, so
    # the REASON is not pinned: malformed_anchor when the recursion fires,
    # wrong_schema when the platform serialises the structure and the cheap head
    # check is what stands. Both are drift verdicts; the contract is a named
    # (ok, reason), never an escape. The RecursionError branch is pinned
    # deterministically in the test below.
    deep = []
    cur = deep
    for _ in range(3000):
        nxt = []
        cur.append(nxt)
        cur = nxt
    rec = {"schema": anchor.SCHEMA,
           "signed_head": {"schema": "nope", "root": deep}}
    r = anchor.verify_anchor(rec, b"\x00" * 32)
    assert r["ok"] is False
    assert isinstance(r["head_reason"], str) and r["head_reason"]


def test_a_recursion_error_from_anchor_digest_is_named_malformed_anchor(monkeypatch):
    # A field nested deep enough trips canonical() inside anchor_digest with
    # RecursionError, which is not a ValueError, so a bare `except ValueError`
    # would let it break the "raises nothing" contract. Whether a real structure
    # trips the interpreter is platform-variant (see the test above), so the branch
    # is pinned directly here: anchor_digest raises RecursionError and the stranger
    # still gets a named drift verdict.
    def boom(_signed_head):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(anchor, "anchor_digest", boom)
    rec = {"schema": anchor.SCHEMA,
           "signed_head": {"schema": "nope", "root": "ab"}}
    r = anchor.verify_anchor(rec, b"\x00" * 32)
    assert r["ok"] is False
    assert "malformed_anchor" in r["head_reason"]


@pytest.mark.parametrize("bad_sig", [123, [1, 2], {"x": 1}, True, None])
def test_verify_anchor_returns_a_verdict_on_a_non_string_signature(bad_sig):
    # A stranger runs verify on an attacker record whose signed_head carries a
    # non-string signature. check_signed_head does bytes.fromhex(signature), which
    # raises TypeError -- a sibling of ValueError -- on int/list/dict/bool/None, and
    # verify_anchor calls check_signed_head outside any try, so the crash escapes
    # the verifier the module docstring promises "raises nothing". The signed_head
    # clears the schema / sig_alg / log_id gates so line 142, not an earlier
    # refusal, is what the call meets. The head check fails; the record is named.
    _, _, pub = _key()
    signed = {"schema": tree_head.SCHEMA, "sig_alg": "ed25519",
              "log_id": tree_head.log_id_for(pub), "size": 1, "root": "ab",
              "timestamp": TS, "signature": bad_sig, "public_key": pub.hex()}
    rec = {"schema": anchor.SCHEMA, "signed_head": signed}
    r = anchor.verify_anchor(rec, pub)
    assert r["ok"] is False
    assert r["head_ok"] is False
    assert "malformed_head" in r["head_reason"]


def test_does_not_prove_carries_the_header_trust_limitation():
    # The proof-of-work recheck bounds internal consistency and real work: it kills
    # the zero-work forgery. It does NOT establish that a bundle-carried header sits
    # on the real Bitcoin chain rather than being a header ground against the
    # maximum target off-chain. That residual limitation must be stated, or a reader
    # over-reads the offline check as chain linkage.
    limits = anchor.does_not_prove()
    header_note = [s for s in limits if "HEADER_IS_A_REAL_BLOCK" in s]
    assert header_note, "the header-trust honest null is missing"
    text = header_note[0].lower()
    assert "source" in text or "chain" in text
