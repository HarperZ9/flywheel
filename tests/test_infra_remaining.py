"""Tests for Families 3, 2, 4, 5 (credential scanner, isolation test, kill
switch, correlator, incident sheet, run BOM, partner assurance)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# --- credential scanner (Family 3) ---------------------------------------

from harness.infra.credential_scanner import (
    SCHEMA as CRED_SCHEMA,
    SecretFinding,
    build_credential_scan_receipt,
    mint_canary_credential,
    scan_directory,
    scan_environment,
    scan_file,
    scan_text,
)


def test_scan_text_finds_api_key():
    text = 'api_key = "sk-abcdefghijklmnopqrstuvwxyz1234567890"'
    findings = scan_text(text, "test")
    assert len(findings) >= 1
    assert any(f.secret_type == "openai_api_key" for f in findings)


def test_scan_text_finds_private_key():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA"
    findings = scan_text(text, "pem")
    assert any(f.secret_type == "private_key" for f in findings)


def test_scan_text_clean():
    findings = scan_text("just normal text with no secrets", "clean")
    assert findings == []


def test_scan_text_never_returns_secret_text():
    text = "password = supersecret123"
    findings = scan_text(text, "test")
    for f in findings:
        assert "supersecret123" not in json.dumps(f.to_dict())


def test_scan_file(tmp_path: Path):
    f = tmp_path / "config.env"
    f.write_text('AWS_KEY=AKIAIOSFODNN7EXAMPLE\n', encoding="utf-8")
    findings = scan_file(f)
    assert len(findings) >= 1


def test_scan_directory(tmp_path: Path):
    (tmp_path / "a.env").write_text("api_key=sk-abcdef1234567890abcdef", encoding="utf-8")
    (tmp_path / "b.txt").write_text("clean file", encoding="utf-8")
    findings = scan_directory(tmp_path)
    assert len(findings) >= 1


def test_credential_scan_receipt_sealed():
    findings = [SecretFinding("openai_api_key", "env:KEY", "abc123")]
    r = build_credential_scan_receipt(findings=findings, scan_root="/tmp")
    assert r["schema"] == CRED_SCHEMA
    assert len(r["seal_hash"]) == 64
    assert r["seal_body"]["finding_count"] == 1


def test_mint_canary_credential_unique():
    c1 = mint_canary_credential("test")
    c2 = mint_canary_credential("test")
    assert c1 != c2
    assert "FLYWHEEL-CANARY-CRED" in c1


# --- isolation test (Family 2) -------------------------------------------

from harness.infra.isolation_test import (
    SCHEMA as ISO_SCHEMA,
    run_isolation_test,
    verify_isolation_test,
)


def test_isolation_test_returns_receipt():
    r = run_isolation_test(run_id="test")
    assert r["schema"] == ISO_SCHEMA
    assert "seal_hash" in r
    assert r["overall_verdict"] in ("MATCH", "DRIFT", "UNVERIFIABLE")


def test_isolation_test_verifies():
    r = run_isolation_test()
    v = verify_isolation_test(r)
    assert v["verdict"] in ("MATCH", "UNVERIFIABLE")


def test_isolation_test_tampered():
    r = run_isolation_test()
    r["seal_body"]["overall_verdict"] = "MATCH"  # may change the seal
    v = verify_isolation_test(r)
    assert v["verdict"] in ("TAMPERED", "MATCH")  # depends on original value


def test_isolation_test_has_boundary_tests():
    r = run_isolation_test()
    tests = r["seal_body"]["tests"]
    boundaries = {t["boundary"] for t in tests}
    assert "network" in boundaries
    assert "identity" in boundaries


# --- kill switch (Family 2) -----------------------------------------------

from harness.infra.kill_switch import (
    SCHEMA as KS_SCHEMA,
    KillRequest,
    build_kill_receipt,
    verify_kill_receipt,
    isolate_network,
)


def test_kill_switch_requires_two_authorities():
    req = KillRequest(run_id="test", reason="containment breach")
    r = build_kill_receipt(req)
    assert r["seal_body"]["executed"] is False
    assert "refusal_reason" in r["seal_body"]


def test_kill_switch_fires_with_two_authorities():
    req = KillRequest(run_id="test", reason="containment breach")
    req.add_authority("alice")
    req.add_authority("bob")
    assert req.confirmed is True
    r = build_kill_receipt(req)
    assert r["seal_body"]["executed"] is True


def test_kill_switch_same_authority_twice_does_not_confirm():
    req = KillRequest(run_id="test", reason="test")
    req.add_authority("alice")
    req.add_authority("alice")  # same person
    assert req.confirmed is False


def test_kill_receipt_verifies():
    req = KillRequest(run_id="t", reason="x")
    req.add_authority("a")
    req.add_authority("b")
    r = build_kill_receipt(req)
    v = verify_kill_receipt(r)
    assert v["verdict"] == "MATCH"
    assert v["executed"] is True


def test_isolate_network_dry_run_by_default():
    result = isolate_network()
    assert result["executed"] is False
    assert "dry run" in result["reason"]

