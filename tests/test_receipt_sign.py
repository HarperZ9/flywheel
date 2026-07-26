"""A signed receipt a stranger checks with the vendored verifier and nothing else.

This is where Bar R stops being a design intention. The verification path must
touch only `harness.ed25519_verify` and `harness.receipt`, both stdlib-only, so a
person who distrusts the author can still establish what the author's machine
concluded.

Four properties:

  1. The signature covers `claim_sha256` and nothing else, per SIGNED_OVER fixed
     in code. Editing any claim field breaks verification.
  2. Editing the RECORDED digest is caught too. A verifier that trusted the
     recorded digest would verify a signature over a number rather than over a
     claim, which is the difference between a receipt and a decoration.
  3. HMAC is local-only. It is refused for export and stripped at pack time,
     because verifying an HMAC requires the secret and a stranger who holds the
     signing secret is not a third party.
  4. An unknown or absent algorithm is UNVERIFIABLE with a reason, never a
     silent pass and never a bare False.
"""
import json

import pytest

from harness.receipt import Receipt, SIGNED_OVER
from harness.receipt_fields import Denominator, EvidenceKind, Tier
from harness.receipt_sign import (
    SignedReceipt, SignError, verify_signed, pack_for_export,
    hmac_sign, ed25519_attach, LOCAL_ONLY_ALGS,
)
from harness.verdict import Verdict, Attribution


def _den():
    return Denominator(
        attempts=8, group_size=4, oracle_calls_consumed=9, hits=1, undecided=0,
        unverifiable=0, parse_failures=0, timeouts=0, tokens_in=120,
        tokens_out=512, cache_hit_tokens=0, tasks_proposed=4,
        tasks_filtered_out=0, filter_id="learn.difficulty.v1",
        filter_hash="sha256:" + "f" * 64, filter_is_learned=False)


def _r(**kw):
    base = dict(
        criterion_id="zarankiewicz.z_2_2", criterion_version=1,
        criterion_sha256="sha256:" + "c" * 64, family="zarankiewicz",
        family_instance_id="z-7", generator_id="g.v1", generator_seed=7,
        candidate_sha256="sha256:" + "d" * 64, prompt_hash="sha256:" + "e" * 64,
        checker_module="harness.certificates.zarankiewicz",
        checker_source_sha256="sha256:" + "a" * 64,
        executes_candidate_code=False, oracle_qa_card_hash="deadbeefdeadbeef",
        held_out_agreement="AGREE", evidence_kind=EvidenceKind.CONSTRUCTIVE,
        tier=Tier.CONSTRUCTION_CERTIFICATE, verdict=Verdict.PASS,
        attribution=Attribution.CANDIDATE, objective="21",
        incumbent_objective="21", incumbent_source="operator_search",
        coverage={"predicate_exact": True, "search_space_enumerated": True,
                  "enumerated_fraction": "1", "stop_reason": "complete",
                  "guarantee_weakens_above": None},
        raw_stdout_sha256="b" * 64, analysis_script_sha256="sha256:" + "9" * 64,
        denominator=_den(), model_ref="gate:deterministic",
        base_weights_digest="", harness_version="phase1b")
    base.update(kw)
    return Receipt(**base)


def _keypair():
    """Signing is dev-side. The vendored module cannot sign, deliberately, so a
    test that needs a signature uses whatever real library is present. This is
    NEVER on the verification path."""
    nacl = pytest.importorskip("nacl.signing")
    sk = nacl.SigningKey.generate()
    return sk, bytes(sk.verify_key)


# --- the happy path -----------------------------------------------------------

def test_a_signed_receipt_verifies():
    sk, pub = _keypair()
    r = _r()
    sig = bytes(sk.sign(r.claim_sha256().encode()).signature)
    signed = ed25519_attach(r, sig, pub, key_id="k1")
    ok, reason = verify_signed(signed.to_dict(), pub)
    assert ok is True
    assert reason == "ok"


def test_the_signature_covers_the_claim_digest_only():
    assert SIGNED_OVER == ("claim_sha256",)
    sk, pub = _keypair()
    r = _r()
    signed = ed25519_attach(
        r, bytes(sk.sign(r.claim_sha256().encode()).signature), pub, key_id="k1")
    assert signed.to_dict()["signature"]["signed_over"] == list(SIGNED_OVER)


def test_verification_touches_only_stdlib_modules():
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "harness" / "receipt_sign.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods <= {"__future__", "hashlib", "hmac", "json", "dataclasses",
                    "receipt", "receipt_fields", "ed25519_verify", "verdict"}, mods


# --- tampering ----------------------------------------------------------------

@pytest.mark.parametrize("field,value", [
    ("verdict", "FAIL"),
    ("objective", "999"),
    ("raw_stdout_sha256", "0" * 64),
    ("held_out_agreement", "NOT_RUN"),
    ("criterion_sha256", "sha256:" + "0" * 64),
])
def test_editing_any_claim_field_breaks_verification(field, value):
    sk, pub = _keypair()
    r = _r()
    signed = ed25519_attach(
        r, bytes(sk.sign(r.claim_sha256().encode()).signature), pub, key_id="k1")
    d = signed.to_dict()
    d["receipt"][field] = value
    ok, reason = verify_signed(d, pub)
    assert ok is False
    assert reason in ("digest_mismatch", "bad_signature")


def test_editing_the_recorded_digest_is_also_caught():
    # A verifier that trusted the recorded claim_sha256 would be verifying a
    # signature over a number rather than over a claim.
    sk, pub = _keypair()
    r = _r()
    signed = ed25519_attach(
        r, bytes(sk.sign(r.claim_sha256().encode()).signature), pub, key_id="k1")
    d = signed.to_dict()
    d["receipt"]["verdict"] = "FAIL"
    d["receipt"]["claim_sha256"] = Receipt.from_dict(d["receipt"]).claim_sha256()
    ok, reason = verify_signed(d, pub)
    # The digest now matches the edited body, so the SIGNATURE must be what fails.
    assert ok is False
    assert reason == "bad_signature"


def test_flipping_a_signature_bit_fails():
    sk, pub = _keypair()
    r = _r()
    sig = bytearray(sk.sign(r.claim_sha256().encode()).signature)
    sig[0] ^= 0x01
    signed = ed25519_attach(r, bytes(sig), pub, key_id="k1")
    ok, reason = verify_signed(signed.to_dict(), pub)
    assert ok is False
    assert reason == "bad_signature"


def test_a_signature_from_a_different_key_fails():
    sk1, pub1 = _keypair()
    _, pub2 = _keypair()
    r = _r()
    signed = ed25519_attach(
        r, bytes(sk1.sign(r.claim_sha256().encode()).signature), pub1,
        key_id="k1")
    ok, reason = verify_signed(signed.to_dict(), pub2)
    assert ok is False


def test_a_signature_for_a_different_receipt_fails():
    sk, pub = _keypair()
    other = _r(objective="7")
    r = _r()
    signed = ed25519_attach(
        r, bytes(sk.sign(other.claim_sha256().encode()).signature), pub,
        key_id="k1")
    ok, reason = verify_signed(signed.to_dict(), pub)
    assert ok is False
    assert reason == "bad_signature"


# --- HMAC is local only --------------------------------------------------------

def test_hmac_signing_is_marked_not_exportable():
    r = _r()
    signed = hmac_sign(r, b"local-secret", key_id="local")
    assert signed.sig_alg in LOCAL_ONLY_ALGS
    assert signed.exportable is False


def test_packing_for_export_strips_a_local_only_signature():
    r = _r()
    signed = hmac_sign(r, b"local-secret", key_id="local")
    packed = pack_for_export(signed.to_dict())
    assert packed["signature"] is None
    assert "LOCAL_SIGNATURE_STRIPPED" in packed["receipt"]["does_not_prove"]
    assert "NOT_THIRD_PARTY_VERIFIABLE_SIGNATURE" in packed["receipt"]["does_not_prove"]


def test_packing_for_export_keeps_an_ed25519_signature():
    sk, pub = _keypair()
    r = _r()
    signed = ed25519_attach(
        r, bytes(sk.sign(r.claim_sha256().encode()).signature), pub, key_id="k1")
    packed = pack_for_export(signed.to_dict())
    assert packed["signature"]["sig_alg"] == "ed25519"
    ok, _ = verify_signed(packed, pub)
    assert ok is True


def test_no_secret_ever_reaches_the_wire_form():
    secret = b"this-must-never-appear"
    signed = hmac_sign(_r(), secret, key_id="local")
    blob = json.dumps(signed.to_dict())
    assert secret.decode() not in blob
    import binascii
    assert binascii.hexlify(secret).decode() not in blob


def test_verifying_an_hmac_receipt_without_the_secret_is_unverifiable():
    signed = hmac_sign(_r(), b"local-secret", key_id="local")
    ok, reason = verify_signed(signed.to_dict(), b"\x00" * 32)
    assert ok is False
    assert reason == "local_only_algorithm"


# --- absent and unknown algorithms --------------------------------------------

def test_an_unsigned_receipt_is_unverifiable_with_a_reason():
    from harness.receipt_sign import unsigned
    ok, reason = verify_signed(unsigned(_r()), b"\x00" * 32)
    assert ok is False
    assert reason == "unsigned"


def test_an_unknown_algorithm_is_refused_not_ignored():
    sk, pub = _keypair()
    r = _r()
    signed = ed25519_attach(
        r, bytes(sk.sign(r.claim_sha256().encode()).signature), pub, key_id="k1")
    d = signed.to_dict()
    d["signature"]["sig_alg"] = "rot13"
    ok, reason = verify_signed(d, pub)
    assert ok is False
    assert reason == "unknown_algorithm"


def test_a_signature_declaring_its_own_coverage_is_refused():
    # signed_over is fixed in code. A receipt that could narrow its own coverage
    # would narrow it to nothing.
    sk, pub = _keypair()
    r = _r()
    signed = ed25519_attach(
        r, bytes(sk.sign(r.claim_sha256().encode()).signature), pub, key_id="k1")
    d = signed.to_dict()
    d["signature"]["signed_over"] = ["family"]
    ok, reason = verify_signed(d, pub)
    assert ok is False
    assert reason == "signed_over_mismatch"


def test_a_malformed_envelope_is_unverifiable_never_true():
    for bad in ({}, {"receipt": {}}, {"signature": {}}, {"receipt": None}):
        ok, reason = verify_signed(bad, b"\x00" * 32)
        assert ok is False


def test_signing_refuses_a_wrong_length_public_key():
    sk, _ = _keypair()
    r = _r()
    with pytest.raises(SignError):
        ed25519_attach(r, bytes(sk.sign(r.claim_sha256().encode()).signature),
                       b"short", key_id="k1")
