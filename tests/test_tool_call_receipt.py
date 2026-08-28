"""Tests for the sealed tool-call receipt (emit + verify + chain)."""
from __future__ import annotations

import json
from pathlib import Path


from harness.tool_call_receipt import (
    BLOCKED,
    COMPLETED,
    MATCH,
    SCHEMA,
    TAMPERED,
    UNVERIFIABLE,
    build_receipt,
    emit_receipt,
    verify_chain,
    verify_receipt,
)

def _sample_receipt(**overrides) -> dict:
    defaults = dict(
        tool="read_file",
        capability="builtin-read",
        admission="ALLOWED",
        args={"path": "/tmp/x.txt"},
        output="hello world",
        ok=True,
        rc=0,
        run_id="run-abc",
        seq=1,
        prev_receipt_sha256="",
        outcome=COMPLETED,
    )
    defaults.update(overrides)
    return build_receipt(**defaults)

def test_build_receipt_produces_sealed_object():
    r = _sample_receipt()
    assert r["schema"] == SCHEMA
    assert r["source"] == "tool:run-abc:1"
    assert r["seal"]["algorithm"] == "sha256"
    assert len(r["seal"]["hex"]) == 64
    assert r["ok"] == "true"  # string, not bool -- no floats in the schema

def test_seal_round_trips():
    r = _sample_receipt()
    v = verify_receipt(r)
    assert v["verdict"] == MATCH
    assert v["outcome"] == COMPLETED

def test_seal_is_deterministic():
    r1 = _sample_receipt()
    r2 = _sample_receipt()
    assert r1["seal"]["hex"] == r2["seal"]["hex"]

def test_seal_changes_with_content():
    r1 = _sample_receipt(output="hello")
    r2 = _sample_receipt(output="goodbye")
    assert r1["seal"]["hex"] != r2["seal"]["hex"]

def test_tampered_output_breaks_seal():
    r = _sample_receipt()
    r["output"]["bytes"] = 999
    v = verify_receipt(r)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"

def test_tampered_seal_hex_breaks_verification():
    r = _sample_receipt()
    r["seal"]["hex"] = "0" * 64
    v = verify_receipt(r)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"

def test_wrong_schema_is_malformed():
    r = _sample_receipt()
    r["schema"] = "wrong"
    v = verify_receipt(r)
    assert v["verdict"] == UNVERIFIABLE
    assert v["failure_class"] == "MALFORMED"

def test_malformed_digest_is_caught():
    r = _sample_receipt()
    # re-seal after tamper so the seal check passes, then corrupt a digest
    r["output"]["sha256"] = "short"
    # need to re-seal to get past seal check -- but the digest check comes after
    # so manually re-seal
    from harness.tool_call_receipt import _canonical_bytes, _sha256_hex
    probe = dict(r)
    probe["seal"] = {"algorithm": "sha256", "hex": ""}
    r["seal"]["hex"] = _sha256_hex(_canonical_bytes(probe))
    v = verify_receipt(r)
    assert v["failure_class"] == "DIGEST_MALFORMED"

def test_blocked_outcome_requires_ok_false():
    r = _sample_receipt(outcome=BLOCKED, ok=False, admission="BLOCKED")
    v = verify_receipt(r)
    assert v["verdict"] == MATCH

def test_blocked_with_ok_true_is_contract_violation():
    r = _sample_receipt(outcome=BLOCKED, ok=True)
    v = verify_receipt(r)
    assert v["failure_class"] == "FIELD_CONTRACT_VIOLATION"

def test_args_never_in_receipt_body():
    r = _sample_receipt(args={"secret": "password123"})
    body = json.dumps(r, sort_keys=True)
    assert "password123" not in body

def test_capability_normalizes_unknown():
    r = _sample_receipt(capability="bogus-capability")
    assert r["capability"] == "unknown"

def test_emit_receipt_writes_file_and_never_raises(tmp_path: Path):
    r = _sample_receipt()
    path = emit_receipt(r, tmp_path / "receipts")
    assert path is not None
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["source"] == r["source"]

def test_emit_receipt_swallows_bad_dir(tmp_path):
    r = _sample_receipt()
    # A path that cannot be created on ANY platform: its parent is a regular
    # file. The previous fixture, /dev/null/subdir, is only invalid on POSIX;
    # on Windows it resolves to a creatable \dev\null\subdir on the current
    # drive, so the "bad dir" quietly became a good one and the first
    # windows-latest CI shard caught the test asserting the wrong world.
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("a file where the receipts dir wants a parent")
    path = emit_receipt(r, blocker / "subdir")
    assert path is None

def test_chain_verifies_linked_receipts():
    r0 = _sample_receipt(seq=0, output="first", prev_receipt_sha256="")
    # compute the prev link for r1: sha256 of r0's canonical sealed bytes
    from harness.tool_call_receipt import _canonical_bytes, _sha256_hex
    probe = dict(r0)
    probe["seal"] = {"algorithm": "sha256", "hex": ""}
    r0_hash = _sha256_hex(_canonical_bytes(probe))
    r1 = _sample_receipt(seq=1, output="second", prev_receipt_sha256=r0_hash)
    result = verify_chain([r0, r1])
    assert result["verdict"] == MATCH
    assert result["n"] == 2

def test_chain_detects_broken_link():
    r0 = _sample_receipt(seq=0, prev_receipt_sha256="")
    r1 = _sample_receipt(seq=1, prev_receipt_sha256="deadbeef" + "0" * 56)
    result = verify_chain([r0, r1])
    assert result["verdict"] == TAMPERED

# --- typed rationale capture -----------------------------------------------

def _rationality_receipt(**overrides) -> dict:
    defaults = dict(
        tool="edit_file",
        capability="builtin-write",
        admission="ALLOWED",
        args={"path": "/tmp/x.txt", "content": "new"},
        output="ok",
        ok=True,
        rc=0,
        run_id="run-rat",
        seq=1,
        prev_receipt_sha256="",
        outcome=COMPLETED,
        rationale={
            "stated_intent": "apply config patch to /tmp/x.txt",
            "options_considered": ["patch", "rebuild", "skip"],
            "chosen_option": "patch",
            "confidence": "moderate",
        },
    )
    defaults.update(overrides)
    return build_receipt(**defaults)

def test_receipt_without_rationale_is_backward_compatible():
    """A receipt built without rationale has no 'rationale' key at all."""
    r = _sample_receipt()
    assert "rationale" not in r
    v = verify_receipt(r)
    assert v["verdict"] == MATCH

def test_receipt_with_rationale_carries_the_block():
    r = _rationality_receipt()
    assert "rationale" in r
    assert r["rationale"]["chosen_option"] == "patch"
    assert r["rationale"]["options_considered"] == ["patch", "rebuild", "skip"]

def test_receipt_with_rationale_verifies():
    r = _rationality_receipt()
    v = verify_receipt(r)
    assert v["verdict"] == MATCH
    assert v.get("has_rationale") is True

def test_receipt_without_rationale_has_no_has_rationale_flag():
    r = _sample_receipt()
    v = verify_receipt(r)
    assert "has_rationale" not in v

def test_rationale_is_sealed_into_the_receipt():
    """Tampering the rationale after sealing breaks the seal."""
    r = _rationality_receipt()
    r["rationale"]["chosen_option"] = "skip"  # tampered
    v = verify_receipt(r)
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"

def test_rationale_changes_the_seal():
    """Different rationale produces a different seal hash."""
    r1 = _rationality_receipt(rationale={
        "stated_intent": "patch", "options_considered": ["patch"],
        "chosen_option": "patch", "confidence": "high"})
    r2 = _rationality_receipt(rationale={
        "stated_intent": "rebuild", "options_considered": ["rebuild"],
        "chosen_option": "rebuild", "confidence": "high"})
    assert r1["seal"]["hex"] != r2["seal"]["hex"]

def test_rationale_normalizes_unknown_fields():
    """Unknown fields are dropped (additionalProperties: false)."""
    r = build_receipt(
        tool="t", capability="builtin-read", admission="ALLOWED",
        args=None, output="ok", ok=True, rc=0, run_id="r", seq=0,
        rationale={"stated_intent": "x", "bogus": "dropped"},
    )
    assert "bogus" not in r["rationale"]
    assert set(r["rationale"].keys()) == {
        "stated_intent", "options_considered", "chosen_option", "confidence"}

def test_rationale_normalizes_options_considered_to_list():
    r = build_receipt(
        tool="t", capability="builtin-read", admission="ALLOWED",
        args=None, output="ok", ok=True, rc=0, run_id="r", seq=0,
        rationale={"stated_intent": "x", "options_considered": "single"},
    )
    assert r["rationale"]["options_considered"] == ["single"]

def test_rationale_with_wrong_fields_fails_verification():
    """A rationale with wrong fields (after sealing) fails structural check."""
    r = _rationality_receipt()
    # Re-seal with a tampered rationale to pass the seal check, then test structure
    r["rationale"] = {"wrong": "shape"}
    from harness.tool_call_receipt import _canonical_bytes, _sha256_hex, _seal_receipt
    _seal_receipt(r)
    v = verify_receipt(r)
    assert v["verdict"] == UNVERIFIABLE
    assert "rationale fields" in v.get("detail", "")

def test_rationale_not_dict_raises():
    import pytest
    with pytest.raises(ValueError):
        build_receipt(
            tool="t", capability="builtin-read", admission="ALLOWED",
            args=None, output="ok", ok=True, rc=0, run_id="r", seq=0,
            rationale="not a dict",
        )

# --- session_token_ref + sandbox --------------------------------------------

def _exec_receipt(**overrides) -> dict:
    defaults = dict(tool="run", capability="builtin-exec", admission="ALLOWED",
        args={"cmd": "echo hi"}, output="hello", ok=True, rc=0, run_id="run_001", seq=0)
    defaults.update(overrides)
    return build_receipt(**defaults)

def test_receipt_with_session_token_ref():
    r = _exec_receipt(session_token_ref="stok_abc123")
    assert r["session_token_ref"] == "stok_abc123"
    assert r["seal"]["hex"]  # still sealed

def test_receipt_without_session_token_is_backward_compatible():
    assert "session_token_ref" not in _exec_receipt()

def test_receipt_with_sandbox_metadata():
    r = _exec_receipt(sandbox={"kind": "windows-low-integrity", "integrity_level": "low"})
    assert r["sandbox"]["kind"] == "windows-low-integrity"
    assert r["seal"]["hex"]

def test_receipt_without_sandbox_is_backward_compatible():
    assert "sandbox" not in _exec_receipt()

def test_receipt_with_session_token_and_sandbox_verifies():
    r = _exec_receipt(session_token_ref="stok_abc123",
        sandbox={"kind": "windows-low-integrity", "integrity_level": "low"})
    assert verify_receipt(r)["verdict"] == MATCH

def test_sandbox_missing_keys_default_to_unknown():
    r = _exec_receipt(sandbox={})
    assert r["sandbox"]["kind"] == "unknown"
    assert r["sandbox"]["integrity_level"] == "unknown"
