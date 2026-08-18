"""Frozen receipts from the pre-fix-round-3 v3 writer."""
from copy import deepcopy
import json
from pathlib import Path

from harness.receipt import LEGACY_SCHEMA, Receipt, SCHEMA
from harness.receipt_sign import pack_for_export, verify_signed


FIXTURE = Path(__file__).parent / "fixtures" / "receipt_v3_legacy_fixtures.json"


def _fixtures():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _envelope(kind):
    frozen = _fixtures()
    return {"schema": frozen[kind]["schema"],
            "receipt": deepcopy(frozen["receipt"]),
            "signature": deepcopy(frozen[kind]["signature"])}


def test_new_claim_bound_limit_writer_uses_a_new_schema():
    assert LEGACY_SCHEMA == "flywheel.receipt/v3"
    assert SCHEMA == "flywheel.receipt/v4"


def test_frozen_legacy_v3_unsigned_receipt_roundtrips_exactly():
    envelope = _envelope("unsigned")
    receipt = Receipt.from_dict(envelope["receipt"])
    assert receipt.claim_sha256() == envelope["receipt"]["claim_sha256"]
    assert receipt.to_dict() == envelope["receipt"]
    assert verify_signed(envelope, b"\x00" * 32) == (False, "unsigned")


def test_frozen_legacy_v3_hmac_export_keeps_the_v3_preimage():
    envelope = _envelope("hmac")
    assert verify_signed(envelope, b"\x00" * 32) == (
        False, "local_only_algorithm")
    exported = pack_for_export(envelope)
    assert exported["signature"] is None
    assert exported["receipt"]["claim_sha256"] == envelope["receipt"]["claim_sha256"]
    assert "extra_does_not_prove" not in exported["receipt"]
    assert "LOCAL_SIGNATURE_STRIPPED" in exported["receipt"]["does_not_prove"]
    assert Receipt.from_dict(exported["receipt"]).to_dict() == exported["receipt"]


def test_frozen_legacy_v3_ed25519_signature_still_verifies():
    envelope = _envelope("ed25519")
    public_key = bytes.fromhex(envelope["signature"]["public_key"])
    assert Receipt.from_dict(envelope["receipt"]).to_dict() == envelope["receipt"]
    assert verify_signed(envelope, public_key) == (True, "ok")
