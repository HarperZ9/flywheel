"""The tree head, signed. What that buys, and what it does not.

The interesting test in this file is the last one. Signing a head does not
PREVENT a log from equivocating. It makes equivocation attributable: two
conflicting heads at the same size, both carrying valid signatures from the same
key, are evidence against the log that no unsigned head could ever provide.
"""
import hashlib

import pytest

from harness.ledger import Ledger
from harness.tree_head import (
    SCHEMA, HEAD_DOMAIN, TreeHeadError, log_id_for, sign_head,
    check_signed_head, head_preimage, does_not_prove,
)


@pytest.fixture
def keys():
    nacl = pytest.importorskip("nacl.signing")
    sk = nacl.SigningKey.generate()
    return sk, bytes(sk.verify_key)


def _signer(sk):
    return lambda msg: bytes(sk.sign(msg).signature)


def _ledger(tmp_path, n=4, log_id=None):
    led = Ledger(tmp_path / "log.jsonl", log_id=log_id)
    for i in range(n):
        led.append_record("receipt", f"sha256:{i:064x}", {"i": i})
    return led


# --- the log id -------------------------------------------------------------

def test_log_id_is_the_sha256_of_the_public_key(keys):
    _, pub = keys
    assert log_id_for(pub) == "sha256:" + hashlib.sha256(pub).hexdigest()


def test_a_log_id_needs_a_real_key():
    with pytest.raises(TreeHeadError):
        log_id_for(b"too short")


# --- signing ----------------------------------------------------------------

def test_a_signed_head_verifies(tmp_path, keys):
    sk, pub = keys
    signed = sign_head(_ledger(tmp_path).head(), _signer(sk),
                       public_key=pub, timestamp="2026-07-26T00:00:00Z")
    assert signed["schema"] == SCHEMA
    assert check_signed_head(signed, pub) == (True, "ok")


def test_a_head_cannot_be_signed_without_a_timestamp(tmp_path, keys):
    sk, pub = keys
    with pytest.raises(TreeHeadError):
        sign_head(_ledger(tmp_path).head(), _signer(sk),
                  public_key=pub, timestamp="")


def test_a_head_missing_its_size_is_refused_not_signed(keys):
    """Signing over an absent field would produce a valid signature on nothing."""
    sk, pub = keys
    with pytest.raises(TreeHeadError):
        sign_head({"root": "sha256:" + "ab" * 32}, _signer(sk),
                  public_key=pub, timestamp="2026-07-26T00:00:00Z")


@pytest.mark.parametrize("field,value", [
    ("size", 99),
    ("root", "sha256:" + "cd" * 32),
    ("timestamp", "2027-01-01T00:00:00Z"),
])
def test_editing_any_signed_field_breaks_the_signature(tmp_path, keys, field, value):
    sk, pub = keys
    signed = sign_head(_ledger(tmp_path).head(), _signer(sk),
                       public_key=pub, timestamp="2026-07-26T00:00:00Z")
    signed[field] = value
    ok, why = check_signed_head(signed, pub)
    assert not ok and why == "bad_signature"


def test_a_head_from_another_log_is_refused_by_log_id(tmp_path, keys):
    nacl = pytest.importorskip("nacl.signing")
    sk, pub = keys
    other = nacl.SigningKey.generate()
    signed = sign_head(_ledger(tmp_path).head(), _signer(sk),
                       public_key=pub, timestamp="2026-07-26T00:00:00Z")
    ok, why = check_signed_head(signed, bytes(other.verify_key))
    assert not ok and why == "log_id_does_not_match_key"


def test_the_verifier_ignores_the_key_packaged_in_the_document(tmp_path, keys):
    """A signature checked against the key beside it proves only that somebody
    owns a key. The trusted key must arrive as an argument."""
    nacl = pytest.importorskip("nacl.signing")
    sk, pub = keys
    attacker = nacl.SigningKey.generate()
    att_pub = bytes(attacker.verify_key)
    honest = sign_head(_ledger(tmp_path).head(), _signer(sk),
                       public_key=pub, timestamp="2026-07-26T00:00:00Z")
    # The attacker rewrites the head and re-signs it with their OWN key, and
    # packages their own public key beside it. Internally consistent.
    forged = sign_head({"size": 999, "root": honest["root"]}, _signer(attacker),
                       public_key=att_pub, timestamp="2026-07-26T00:00:00Z")
    assert check_signed_head(forged, att_pub) == (True, "ok")   # self-consistent
    ok, why = check_signed_head(forged, pub)                    # but not OUR log
    assert not ok and why == "log_id_does_not_match_key"


# --- domain separation against receipt signatures ---------------------------

def test_a_digest_signature_cannot_be_replayed_as_a_head_signature(keys):
    """Both are Ed25519 over bytes we chose. `receipt_sign` signs a bare claim
    digest string; without a distinct prefix here, such a signature could cross
    into the head space and attest to a tree its signer never saw."""
    sk, pub = keys
    root = "sha256:" + "11" * 32
    # Exactly the shape receipt_sign.py signs: the digest string, no prefix.
    digest_sig = bytes(sk.sign(root.encode()).signature)
    head = {"schema": SCHEMA, "log_id": log_id_for(pub), "size": 1,
            "root": root, "timestamp": "2026-07-26T00:00:00Z",
            "signature": digest_sig.hex(), "public_key": pub.hex(),
            "sig_alg": "ed25519"}
    ok, why = check_signed_head(head, pub)
    assert not ok and why == "bad_signature"
    assert head_preimage(head).startswith(HEAD_DOMAIN)


def test_check_signed_head_returns_a_verdict_on_a_deeply_nested_field(keys):
    """A stranger runs this on an attacker-supplied head; it must stay (ok, reason).

    A SIGNED_OVER field nested past the interpreter's recursion limit makes
    canonical() inside head_preimage raise RecursionError, which is not a
    ValueError, so the `except (TreeHeadError, ValueError)` below head_preimage
    would let it escape and break the contract the docstring promises. The head
    clears the cheap schema / sig_alg / log_id gates, so the recursion -- not an
    earlier refusal -- is what the call meets. The signature is never reached.
    """
    _, pub = keys
    deep = []
    cur = deep
    for _ in range(3000):
        nxt = []
        cur.append(nxt)
        cur = nxt
    head = {"schema": SCHEMA, "sig_alg": "ed25519", "log_id": log_id_for(pub),
            "size": 1, "root": deep, "timestamp": "2026-08-29T00:00:00Z",
            "signature": "00" * 64, "public_key": pub.hex()}
    ok, reason = check_signed_head(head, pub)
    assert ok is False
    assert "malformed_head" in reason


@pytest.mark.parametrize("bad_sig", [123, [1, 2], {"x": 1}, True, None])
def test_check_signed_head_returns_a_verdict_on_a_non_string_signature(
        keys, bad_sig):
    """A stranger runs this on an attacker-supplied head; it must stay (ok, reason).

    bytes.fromhex on a non-string `signature` raises TypeError, a sibling of
    ValueError rather than a subclass, so the `except (TreeHeadError, ValueError,
    RecursionError)` below head_preimage lets it escape. json.loads yields
    int / list / dict / bool / None for a signature field, and each is present (so
    the .get default does not apply). The head clears the cheap schema / sig_alg /
    log_id gates -- log_id is just sha256 of the public key, which is public -- so
    line 142, not an earlier refusal, is what the call meets.
    """
    _, pub = keys
    head = {"schema": SCHEMA, "sig_alg": "ed25519", "log_id": log_id_for(pub),
            "size": 1, "root": "ab", "timestamp": "2026-08-29T00:00:00Z",
            "signature": bad_sig, "public_key": pub.hex()}
    ok, reason = check_signed_head(head, pub)
    assert ok is False
    assert "malformed_head" in reason


# --- what the ledger now carries --------------------------------------------

def test_proofs_carry_the_log_id_when_the_ledger_has_one(tmp_path, keys):
    _, pub = keys
    lid = log_id_for(pub)
    led = _ledger(tmp_path, log_id=lid)
    h0 = led.head()
    assert led.proof_for("sha256:" + f"{1:064x}")["log_id"] == lid
    led.append_record("receipt", "sha256:" + "ff" * 32, {"late": True})
    assert led.consistency_since(h0)["log_id"] == lid


def test_a_keyless_ledger_reports_no_log_id_and_says_so(tmp_path):
    led = _ledger(tmp_path)
    assert led.proof_for("sha256:" + f"{1:064x}")["log_id"] is None
    assert "NOT_PROVES_WHICH_LOG" in led.does_not_prove()


# --- the property this module exists for ------------------------------------

def test_signing_makes_equivocation_attributable_rather_than_impossible(
        tmp_path, keys):
    """The honest statement of what a signed head buys.

    A log CAN still show two views. What it cannot do is deny having shown them:
    both heads carry its signature, so the pair is evidence. An unsigned head
    gives a stranger nothing to hold, because either view could be attributed to
    whoever handed it over.
    """
    sk, pub = keys
    ts = "2026-07-26T00:00:00Z"
    real = _ledger(tmp_path, log_id=log_id_for(pub)).head()
    lie = dict(real, root="sha256:" + "ee" * 32)      # same size, other root

    a = sign_head(real, _signer(sk), public_key=pub, timestamp=ts)
    b = sign_head(lie, _signer(sk), public_key=pub, timestamp=ts)

    # Each verifies on its own. Signing does not prevent the second view.
    assert check_signed_head(a, pub) == (True, "ok")
    assert check_signed_head(b, pub) == (True, "ok")

    # Held together they are proof of equivocation, attributable to one key.
    assert a["size"] == b["size"] and a["root"] != b["root"]
    assert a["log_id"] == b["log_id"]

    # And the module says this out loud rather than implying it was solved.
    assert any("NOT_PROVES_NON_EQUIVOCATION_ALONE" in d for d in does_not_prove())
