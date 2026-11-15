import sys
import time
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from env_authority import AuthorityGrant, SCHEMA
from authority_gate import (
    GateResult,
    check_entitlement,
    gate_infer,
    gate_inoculate,
    gate_launch,
    gate_seal,
    require,
)


def _make_grant(
    status="authorized",
    seal="pass",
    entitlements=None,
    surface="claude_code",
    ttl=3600,
):
    now = time.time()
    return AuthorityGrant(
        schema=SCHEMA,
        status=status,
        operator_fingerprint="test_op_fp",
        machine_fingerprint="test_mach_fp",
        capsule_sha256="test_capsule",
        seal_status=seal,
        surface=surface,
        entitlements=entitlements or ["transform", "infer", "scan"],
        issued_at=now,
        expires_at=now + ttl if status == "authorized" else 0,
    )


def test_check_entitlement_allows_valid():
    grant = _make_grant()
    result = check_entitlement("transform", gate="test", grant=grant)
    assert result.allowed is True
    assert result.gate == "test"
    assert result.entitlement == "transform"


def test_check_entitlement_denies_missing():
    grant = _make_grant(entitlements=["transform"])
    result = check_entitlement("inoculate", gate="test", grant=grant)
    assert result.allowed is False
    assert "entitlement_missing" in result.reason


def test_check_entitlement_denies_expired():
    grant = _make_grant(ttl=-100)
    result = check_entitlement("transform", gate="test", grant=grant)
    assert result.allowed is False
    assert "grant_expired" in result.reason


def test_check_entitlement_denies_unauthorized():
    grant = _make_grant(status="unauthorized")
    result = check_entitlement("transform", gate="test", grant=grant)
    assert result.allowed is False
    assert "unauthorized" in result.reason


def test_gate_infer_with_entitlement():
    grant = _make_grant(entitlements=["infer"])
    result = gate_infer(grant=grant)
    assert result.allowed is True
    assert result.gate == "infer"


def test_gate_inoculate_denied_for_non_warden():
    grant = _make_grant(surface="claude_code", entitlements=["transform", "infer"])
    result = gate_inoculate(grant=grant)
    assert result.allowed is False


def test_gate_seal_allowed_for_warden():
    grant = _make_grant(surface="warden_cli", entitlements=["seal", "transform"])
    result = gate_seal(grant=grant)
    assert result.allowed is True


def test_require_raises_on_denial():
    grant = _make_grant(status="unauthorized")
    with pytest.raises(PermissionError, match="gate:test denied"):
        require("transform", gate="test", grant=grant)


def test_require_returns_result_on_success():
    grant = _make_grant()
    result = require("transform", gate="test", grant=grant)
    assert isinstance(result, GateResult)
    assert result.allowed is True


def test_gate_result_to_dict():
    grant = _make_grant()
    result = check_entitlement("infer", gate="cli", grant=grant)
    d = result.to_dict()
    assert d["allowed"] is True
    assert d["gate"] == "cli"
    assert d["operator_fingerprint"] == "test_op_fp"
    assert d["checked_at"] > 0


def test_authority_cli_runs():
    from bt_cli import main as bt_main
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        bt_main(["authority", "--surface", "generic_cli"])
    finally:
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
    assert "Status:" in output
    assert "Surface:" in output


def test_gate_cli_runs():
    from bt_cli import main as bt_main
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        bt_main(["gate", "transform"])
    finally:
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
    assert "transform" in output
