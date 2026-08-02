"""Interop tests for sealed TADR receipts on the Proof Surface spine."""
from __future__ import annotations

import pytest

import harness.governance.tadr_receipt as tadr_receipt
from harness.governance.tadr_interop import classification_entry, control_entry
from harness.governance.tadr_receipt import (
    build_classification_receipt,
)


def _classification(status: str = "active") -> dict:
    return build_classification_receipt(
        tier="T2", modifiers=["A"], system_id="system-1",
        consequence_analysis="bounded agent capability", status=status)


def _control(observations: list[dict] | None = None) -> dict:
    return tadr_receipt.build_control_receipt(
        system_id="system-1", classification_ref=_classification()["seal_hash"],
        tier="T2", observations=observations or [],
        checked_at="2026-08-02T00:00:00Z", checker_id="baseline-check/v1")


def test_classification_entry_requires_separate_trusted_authority_match():
    assert classification_entry(_classification())["status"] == "unverified"
    assert classification_entry(
        _classification(), trusted_authority_verdict="UNVERIFIABLE"
    )["status"] == "unverified"
    assert classification_entry(
        _classification(), trusted_authority_verdict="MATCH"
    )["status"] == "pass"


def test_classification_entry_tamper_never_passes():
    receipt = _classification()
    receipt["seal_body"]["tier"] = "T3"
    entry = classification_entry(receipt, trusted_authority_verdict="MATCH")
    assert entry["status"] == "unverified"


def test_control_entry_rejects_missing_or_zero_seal():
    with pytest.raises(ValueError, match="seal"):
        control_entry({"schema": "flywheel.tadr-control/v1"})
    receipt = _control()
    receipt["seal_hash"] = "0" * 64
    with pytest.raises(ValueError, match="seal"):
        control_entry(receipt)


def test_control_entry_uses_verified_nonzero_seal():
    entry = control_entry(_control())
    assert entry["payload_sha256"] != "0" * 64
    assert entry["status"] == "unverified"


def test_entries_validate_with_installed_proof_surface():
    proof_surface = pytest.importorskip("proof_surface")
    receipt_kinds = pytest.importorskip(
        "proof_surface.organ_receipt_bundle").RECEIPT_KINDS
    if "tadr-control" not in receipt_kinds:
        pytest.skip("installed Proof Surface predates TADR receipt kinds")
    bundle = {
        "organ_bundle_version": "0.1", "bundle_id": "bundle-1",
        "generated_at": "2026-08-02T00:00:00Z", "subject": "system-1",
        "entries": [
            classification_entry(_classification()),
            control_entry(_control()),
        ],
    }
    assert proof_surface.validate_organ_receipt_bundle(bundle) == []
