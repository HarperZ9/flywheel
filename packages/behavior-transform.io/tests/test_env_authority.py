import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from env_authority import (
    AuthorityGrant,
    MachineFingerprint,
    SCHEMA,
    SURFACE_ENTITLEMENTS,
    derive_machine_fingerprint,
    derive_operator_fingerprint,
    resolve_authority,
)


def test_machine_fingerprint_deterministic():
    fp1 = derive_machine_fingerprint()
    fp2 = derive_machine_fingerprint()
    assert fp1.digest == fp2.digest
    assert len(fp1.digest) == 16


def test_machine_fingerprint_fields():
    fp = derive_machine_fingerprint()
    assert fp.node_name
    assert fp.platform
    assert fp.machine
    d = fp.to_dict()
    assert set(d.keys()) == {"node_name", "platform", "machine", "digest"}


def test_operator_fingerprint_binds_machine_and_capsule():
    fp = derive_machine_fingerprint()
    op1 = derive_operator_fingerprint(fp, "capsule_aaa")
    op2 = derive_operator_fingerprint(fp, "capsule_bbb")
    assert op1 != op2
    assert len(op1) == 24


def test_authority_grant_valid_when_authorized():
    now = time.time()
    grant = AuthorityGrant(
        schema=SCHEMA,
        status="authorized",
        operator_fingerprint="abc123",
        machine_fingerprint="def456",
        capsule_sha256="sha",
        seal_status="pass",
        surface="claude_code",
        entitlements=["transform", "infer"],
        issued_at=now,
        expires_at=now + 3600,
    )
    assert grant.valid is True
    assert grant.expired is False
    assert grant.has_entitlement("transform") is True
    assert grant.has_entitlement("inoculate") is False


def test_authority_grant_invalid_when_expired():
    now = time.time()
    grant = AuthorityGrant(
        schema=SCHEMA,
        status="authorized",
        operator_fingerprint="abc123",
        machine_fingerprint="def456",
        capsule_sha256="sha",
        seal_status="pass",
        surface="claude_code",
        entitlements=["transform"],
        issued_at=now - 7200,
        expires_at=now - 3600,
    )
    assert grant.valid is False
    assert grant.expired is True
    assert grant.has_entitlement("transform") is False


def test_authority_grant_invalid_when_unauthorized():
    now = time.time()
    grant = AuthorityGrant(
        schema=SCHEMA,
        status="unauthorized",
        operator_fingerprint="",
        machine_fingerprint="def456",
        capsule_sha256="",
        seal_status="unavailable",
        surface="generic_cli",
        entitlements=[],
        issued_at=now,
        expires_at=0,
    )
    assert grant.valid is False
    assert grant.has_entitlement("transform") is False


def test_surface_projection_hides_internals():
    now = time.time()
    grant = AuthorityGrant(
        schema=SCHEMA,
        status="authorized",
        operator_fingerprint="secret_fp",
        machine_fingerprint="machine_fp",
        capsule_sha256="capsule_hash",
        seal_status="pass",
        surface="claude_code",
        entitlements=["transform", "infer", "scan"],
        issued_at=now,
        expires_at=now + 3600,
    )
    proj = grant.surface_projection()
    assert proj["authorization_status"] == "verified"
    assert proj["entitlement_count"] == 3
    assert "secret_fp" not in str(proj)
    assert "capsule_hash" not in str(proj)


def test_to_dict_includes_all_fields():
    now = time.time()
    grant = AuthorityGrant(
        schema=SCHEMA,
        status="authorized",
        operator_fingerprint="op",
        machine_fingerprint="mach",
        capsule_sha256="cap",
        seal_status="pass",
        surface="warden_cli",
        entitlements=["seal"],
        issued_at=now,
        expires_at=now + 60,
    )
    d = grant.to_dict()
    assert d["schema"] == SCHEMA
    assert d["valid"] is True
    assert d["expired"] is False
    assert "seal" in d["entitlements"]


def test_resolve_authority_without_capsule(monkeypatch):
    monkeypatch.setenv("WARDEN_CAPSULE_SHA256", "")
    monkeypatch.delenv("WARDEN_PREFIRE_SURFACE", raising=False)
    grant = resolve_authority(surface="generic_cli")
    assert grant.status == "unauthorized"
    assert grant.entitlements == []


def test_resolve_authority_with_env_capsule(monkeypatch):
    monkeypatch.setenv("WARDEN_CAPSULE_SHA256", "abcdef1234567890")
    monkeypatch.delenv("WARDEN_PREFIRE_SURFACE", raising=False)
    grant = resolve_authority(surface="claude_code")
    assert grant.operator_fingerprint
    assert grant.capsule_sha256 == "abcdef1234567890"
    if grant.seal_status in ("pass", "unavailable"):
        assert grant.status == "authorized"
        assert "transform" in grant.entitlements
    else:
        assert grant.status == "unauthorized"


def test_surface_entitlements_scoping():
    assert "inoculate" not in SURFACE_ENTITLEMENTS["generic_cli"]
    assert "inoculate" in SURFACE_ENTITLEMENTS["warden_cli"]
    assert "infer" not in SURFACE_ENTITLEMENTS["generic_cli"]
    assert "infer" in SURFACE_ENTITLEMENTS["claude_code"]
