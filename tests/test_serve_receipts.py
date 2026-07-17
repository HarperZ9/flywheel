"""Falsifier for serve-side receipt minting on /chat/completions and /generate
(SUPERAPP.md increment 3). No model or GPU needed: the receipt is a pure function
of (request parts, response, served weights ref), so it is tested on a synthetic
payload exactly as the handler builds it.

Load-bearing: (1) the receipt_id RECOMPUTES from its recorded parts -- a third
party re-derives it; (2) it MOVES when the response changes; (3) it MOVES when the
served weights ref changes (a different GGUF -> a different receipt); (4) the
weights fingerprint binds into the receipt when configured, and is honestly absent
when not.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import serve
from harness.messages_api import make_receipt

_MINT = serve._H._mint_receipt


def _payload(text="def f():\n    return 1\n", ref="14b (nf4)", seed=0):
    return {"text": text, "seed": seed, "model_ref": ref, "prompt_hash": "abc0000000000000"}


def test_receipt_recomputes_from_recorded_parts():
    p = _payload()
    r = _MINT("the prompt", "sys", 128, 0.0, 0, p)
    expect = make_receipt(
        {"prompt": "the prompt", "system": "sys", "max_new_tokens": 128,
         "temperature": 0.0, "seed": 0}, p, p["model_ref"])
    assert r["receipt_id"] == expect["receipt_id"]     # third party re-derives it


def test_receipt_moves_when_response_changes():
    a = _MINT("p", "s", 128, 0.0, 0, _payload(text="A"))
    b = _MINT("p", "s", 128, 0.0, 0, _payload(text="B"))
    assert a["receipt_id"] != b["receipt_id"]


def test_receipt_moves_when_request_changes():
    a = _MINT("prompt one", "s", 128, 0.0, 0, _payload())
    b = _MINT("prompt two", "s", 128, 0.0, 0, _payload())
    assert a["receipt_id"] != b["receipt_id"]


def test_receipt_moves_when_weights_ref_changes():
    a = _MINT("p", "s", 128, 0.0, 0, _payload(ref="Qwen2.5-Coder-14B (nf4)"))
    b = _MINT("p", "s", 128, 0.0, 0, _payload(ref="Qwen2.5-Coder-32B (nf4)"))
    assert a["receipt_id"] != b["receipt_id"]          # different GGUF -> different receipt


def test_weights_sha_binds_when_configured(monkeypatch):
    monkeypatch.setattr(serve, "ARTIFACT_SHA256", "613db240cafef00d")
    r = _MINT("p", "s", 128, 0.0, 0, _payload())
    assert r["weights_sha256"] == "613db240cafef00d"


def test_weights_sha_absent_when_unset(monkeypatch):
    monkeypatch.setattr(serve, "ARTIFACT_SHA256", "")
    r = _MINT("p", "s", 128, 0.0, 0, _payload())
    assert "weights_sha256" not in r                   # honest absence, not a fake value


def test_weights_sha_is_folded_into_receipt_id(monkeypatch):
    # The fingerprint must be RE-CHECKABLE, not a write-only field: two weight files
    # that share a MODEL_REF but differ in artifact hash must get DISTINCT receipt_ids,
    # and tampering the stored fingerprint must break the recompute.
    p = _payload(ref="same-ref (nf4)")
    monkeypatch.setattr(serve, "ARTIFACT_SHA256", "weightsAAAA")
    a = _MINT("p", "s", 128, 0.0, 0, p)
    monkeypatch.setattr(serve, "ARTIFACT_SHA256", "weightsBBBB")
    b = _MINT("p", "s", 128, 0.0, 0, p)
    assert a["receipt_id"] != b["receipt_id"]          # different weights -> different id
    # tamper: editing weights_sha256 must change the recomputed id (make_receipt is the re-check)
    recompute = make_receipt(
        {"prompt": "p", "system": "s", "max_new_tokens": 128, "temperature": 0.0, "seed": 0},
        p, p["model_ref"], "weightsBBBB")
    assert recompute["receipt_id"] == b["receipt_id"]  # honest recompute matches
    assert recompute["receipt_id"] != a["receipt_id"]  # a forged fingerprint would not


def test_idempotent_same_turn_same_id():
    p = _payload()
    a = _MINT("p", "s", 128, 0.0, 0, p)
    b = _MINT("p", "s", 128, 0.0, 0, p)
    assert a["receipt_id"] == b["receipt_id"]          # content-addressed, idempotent
