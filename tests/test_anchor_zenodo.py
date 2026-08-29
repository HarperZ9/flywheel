"""Bind a Zenodo DOI to the anchor digest, so the durability leg and the Bitcoin
leg witness the SAME bytes.

`anchor.py` computes one digest: sha256 over the canonical signed head. The
Bitcoin timestamp covers that digest. For the DOI to be the second witness over
the same fact, the file deposited at Zenodo must be exactly those canonical bytes,
so a stranger downloads the DOI's file, hashes it, and gets the digest the
OpenTimestamps proof starts from. These tests pin that the producer emits exactly
those bytes, that the binding check accepts them and rejects anything else, and
that a record whose digest_hex disagrees with its own head is refused before any
network call.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import anchor as anchor_mod  # noqa: E402
from harness import anchor_zenodo  # noqa: E402
from harness import zenodo_deposit  # noqa: E402
from harness.receipt_fields import canonical  # noqa: E402


class FakeTransport:
    """Records every call and returns programmed (status, body) replies in order."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []

    def __call__(self, method, url, *, headers=None, body=None):
        self.calls.append((method, url, dict(headers or {}), body))
        status, payload = self._replies.pop(0)
        if isinstance(payload, (bytes, bytearray)):
            return status, bytes(payload)
        return status, json.dumps(payload).encode()


def _signed_head():
    """A head shaped like a signed tree head. The binding never checks the
    signature, only the digest over the canonical bytes, so a placeholder sig is
    enough to exercise it."""
    return {"schema": "flywheel.tree_head/v1", "n": 3,
            "root": "aa" * 32, "timestamp": "2026-08-28T00:00:00Z",
            "public_key": "bb" * 32, "sig": "cc" * 64}


def _anchor():
    return anchor_mod.build_anchor(_signed_head())


TOKEN = "tok_ABC123_never_in_url"


def _created(dep_id=77, base="https://sandbox.zenodo.org/api"):
    self_url = f"{base}/deposit/depositions/{dep_id}"
    return {"id": dep_id, "links": {
        "self": self_url,
        "bucket": f"{base}/files/bucket-{dep_id}",
        "publish": f"{self_url}/actions/publish"}}


def _md():
    return zenodo_deposit.build_metadata(title="Flywheel anchor", description="d",
                                         creators=[{"name": "Harper, Zain Dana"}])


# ---- the producer: exact bytes -----------------------------------------

def test_deposit_bytes_are_the_canonical_head_and_hash_to_the_digest():
    rec = _anchor()
    name, data = anchor_zenodo.deposit_bytes(rec)
    assert data == canonical(rec["signed_head"]).encode()
    assert hashlib.sha256(data).hexdigest() == rec["digest_hex"]
    assert name.endswith(".json")


def test_deposit_bytes_refuses_a_record_whose_digest_disagrees_with_its_head():
    import pytest
    rec = _anchor()
    rec["digest_hex"] = "00" * 32  # digest no longer matches the head it carries
    with pytest.raises(zenodo_deposit.DepositError):
        anchor_zenodo.deposit_bytes(rec)


def test_deposit_bytes_refuses_a_record_whose_head_was_altered_after_digesting():
    import pytest
    rec = _anchor()
    rec["signed_head"]["root"] = "ff" * 32  # head changed, digest_hex stale
    with pytest.raises(zenodo_deposit.DepositError):
        anchor_zenodo.deposit_bytes(rec)


def test_deposit_bytes_refuses_a_record_whose_prefixed_anchor_digest_was_tampered():
    # The record carries the digest twice: digest_hex (bare) and anchor_digest
    # ("sha256:"-prefixed). The docstring promises a tampered record never reaches
    # the network, so a record whose prefixed field disagrees with its head must be
    # refused even when the bare field still matches.
    import pytest
    rec = _anchor()
    rec["anchor_digest"] = "sha256:" + "00" * 32  # prefixed field now lies
    with pytest.raises(zenodo_deposit.DepositError):
        anchor_zenodo.deposit_bytes(rec)


# ---- the stranger's check ----------------------------------------------

def test_check_binding_accepts_the_matching_bytes_and_rejects_others():
    rec = _anchor()
    _name, data = anchor_zenodo.deposit_bytes(rec)
    ok, reason = anchor_zenodo.check_binding(data, rec)
    assert ok is True
    bad_ok, bad_reason = anchor_zenodo.check_binding(data + b"x", rec)
    assert bad_ok is False and bad_reason


def test_check_binding_re_derives_from_the_head_and_ignores_a_tampered_digest_hex():
    # The stranger must not trust the record's self-reported digest. If digest_hex
    # is edited to match forged bytes, check_binding must still refuse them: the
    # authoritative digest is sha256 over the record's own signed head, which is
    # what verify_anchor and the OpenTimestamps proof are anchored to.
    rec = _anchor()
    forged = b'{"not":"the signed head"}'
    rec["digest_hex"] = hashlib.sha256(forged).hexdigest()  # the record now lies
    ok, reason = anchor_zenodo.check_binding(forged, rec)
    assert ok is False and reason
    # the genuine head bytes still verify, against the head-derived digest
    good = canonical(rec["signed_head"]).encode()
    assert anchor_zenodo.check_binding(good, rec)[0] is True


# ---- the convenience: deposit exactly the bound bytes ------------------

def test_deposit_anchor_uploads_the_bound_bytes_and_reports_the_digest():
    rec = _anchor()
    _name, data = anchor_zenodo.deposit_bytes(rec)
    ft = FakeTransport([
        (201, _created()),              # create
        (201, {"key": "signed-head.json"}),  # upload
        (200, _created()),              # set metadata
    ])
    res = anchor_zenodo.deposit_anchor(
        ft, rec, token=TOKEN, metadata=_md(), sandbox=True, publish=False)
    assert res["published"] is False
    assert res["anchor_digest"] == rec["anchor_digest"]
    assert res["digest_hex"] == rec["digest_hex"]
    # the uploaded body is exactly the canonical head bytes
    put = [c for c in ft.calls if c[0] == "PUT" and "/files/" in c[1]]
    assert len(put) == 1
    assert put[0][3] == data


def test_deposit_anchor_result_surfaces_the_binding_specific_caveats():
    # This codebase delivers its honest nulls. deposit_anchor must surface the
    # binding-specific caveats, not only the durability caveats deposit() already
    # carries, so a caller sees that a DOI orders nothing on its own.
    rec = _anchor()
    ft = FakeTransport([
        (201, _created()),
        (201, {"key": "signed-head.json"}),
        (200, _created()),
    ])
    res = anchor_zenodo.deposit_anchor(ft, rec, token=TOKEN, metadata=_md(),
                                       sandbox=True, publish=False)
    joined = " ".join(res["does_not_prove"])
    assert "NOT_PROVES_THE_TIMESTAMP" in joined  # binding caveat, surfaced here
    assert "NOT_PROVES_TIME" in joined           # durability caveat, still present


def test_deposit_anchor_never_puts_the_token_in_any_url():
    rec = _anchor()
    ft = FakeTransport([
        (201, _created()),
        (201, {"key": "signed-head.json"}),
        (200, _created()),
    ])
    anchor_zenodo.deposit_anchor(ft, rec, token=TOKEN, metadata=_md(),
                                 sandbox=True, publish=False)
    for (_m, url, headers, _b) in ft.calls:
        assert TOKEN not in url
        assert headers["Authorization"] == f"Bearer {TOKEN}"
