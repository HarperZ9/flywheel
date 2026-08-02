"""Tests for egress matrix, egress monitor, and reality contract (Family 1)."""
from __future__ import annotations

import json

import pytest

from harness.infra.egress import (
    SCHEMA as EGRESS_SCHEMA,
    build_egress_receipt,
    scan_egress,
    verify_egress_receipt,
)
from harness.infra.egress_matrix import (
    EgressMatrix,
    EgressRule,
    default_matrix,
)
from harness.infra.reality_contract import (
    SCHEMA as RC_SCHEMA,
    RealityContract,
    collision_test,
    default_evaluation_contract,
)


# --- egress matrix --------------------------------------------------------


def test_default_matrix_allows_localhost():
    m = default_matrix()
    result = m.check("127.0.0.1", 8080)
    assert result["verdict"] == "ALLOWED"


def test_default_matrix_allows_pypi():
    m = default_matrix()
    result = m.check("pypi.org", 443, "https")
    assert result["verdict"] == "ALLOWED"
    assert "package" in result["purpose"]


def test_default_matrix_blocks_cloud_metadata():
    m = default_matrix()
    result = m.check("169.254.169.254", 80)
    assert result["verdict"] == "BLOCKED"


def test_strict_matrix_blocks_unknown():
    m = default_matrix(strict=True)
    result = m.check("evil.example.com", 4444)
    assert result["verdict"] == "BLOCKED"


def test_non_strict_matrix_unknown_for_unlisted():
    m = default_matrix(strict=False)
    result = m.check("random.example.com", 4444)
    assert result["verdict"] == "UNKNOWN"


def test_wildcard_pattern_matches():
    rule = EgressRule(pattern="*.pypi.org", port="443")
    assert rule.matches("files.pypi.org", 443, "tcp")
    assert rule.matches("pypi.org", 443, "tcp")  # apex also matches


def test_matrix_to_dict_round_trips():
    m = default_matrix()
    d = m.to_dict()
    assert "rules" in d
    assert len(d["rules"]) > 0


# --- egress receipts ------------------------------------------------------


def test_build_egress_receipt_is_sealed():
    r = build_egress_receipt(
        destination="pypi.org", port=443, protocol="tcp",
        process="python", pid=1234, verdict="ALLOWED",
        reason="", purpose="package registry", run_id="test")
    assert r["schema"] == EGRESS_SCHEMA
    assert len(r["seal_hash"]) == 64


def test_verify_egress_receipt_match():
    r = build_egress_receipt(
        destination="127.0.0.1", port=8080, protocol="tcp",
        process="python", pid=1, verdict="ALLOWED",
        reason="", purpose="localhost", run_id="test")
    v = verify_egress_receipt(r)
    assert v["verdict"] == "MATCH"
    assert v["egress_verdict"] == "ALLOWED"


def test_verify_egress_receipt_tampered():
    r = build_egress_receipt(
        destination="127.0.0.1", port=8080, protocol="tcp",
        process="python", pid=1, verdict="ALLOWED",
        reason="", purpose="localhost", run_id="test")
    r["seal_body"]["verdict"] = "BLOCKED"
    v = verify_egress_receipt(r)
    assert v["verdict"] == "TAMPERED"


def test_verify_egress_receipt_bad_verdict():
    r = build_egress_receipt(
        destination="x", port=1, protocol="tcp",
        process="p", pid=0, verdict="ALLOWED",
        reason="", purpose="", run_id="t")
    r["seal_body"]["verdict"] = "BOGUS"
    import hashlib
    from harness.infra.egress import _canonical_bytes, _sha256_hex
    r["seal_hash"] = _sha256_hex(_canonical_bytes(r["seal_body"]))
    v = verify_egress_receipt(r)
    assert v["verdict"] == "UNVERIFIABLE"


def test_scan_egress_returns_receipts():
    """scan_egress runs without crashing and returns a list."""
    receipts = scan_egress(default_matrix(), run_id="test")
    assert isinstance(receipts, list)
    # Each receipt (if any) should verify
    for r in receipts:
        v = verify_egress_receipt(r)
        assert v["verdict"] == "MATCH"


# --- reality contract ----------------------------------------------------


def test_reality_contract_allows_approved():
    c = default_evaluation_contract()
    result = c.check_target("sim-target-1.eval")
    assert result["status"] in ("allowed", "simulated")


def test_reality_contract_prohibits_metadata():
    c = default_evaluation_contract()
    result = c.check_target("169.254.169.254")
    assert result["status"] == "prohibited"


def test_reality_contract_needs_human_for_unknown():
    c = default_evaluation_contract()
    result = c.check_target("random-real-bank.com")
    assert result["status"] == "needs-human"


def test_reality_contract_verify_challenge_match():
    c = default_evaluation_contract()
    result = c.verify_challenge(c.challenge_marker)
    assert result["status"] == "verified"


def test_reality_contract_verify_challenge_drift():
    c = default_evaluation_contract()
    result = c.verify_challenge("wrong-marker")
    assert result["status"] == "drift"


def test_collision_test_finds_clashes():
    c = RealityContract(
        simulated_targets=["google.eval", "fake-amazon.test"],
    )
    collisions = collision_test(c, ["google", "amazon"])
    assert len(collisions) == 2


def test_collision_test_clean():
    c = RealityContract(
        simulated_targets=["sim-target-1.eval", "test-db.local"],
    )
    collisions = collision_test(c, ["google", "amazon", "microsoft"])
    assert collisions == []


def test_reality_contract_to_dict_has_schema():
    c = default_evaluation_contract()
    d = c.to_dict()
    assert d["schema"] == RC_SCHEMA
    assert d["environment_label"] == "evaluation"
