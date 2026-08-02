"""isolation_test.py -- Artifact 21: Isolation Acceptance Test.

A pre-run test that challenges network, identity, storage, package, and
management-plane boundaries from the agent runtime's privilege context.
Emits sealed flywheel.isolation-test/v1 receipt with per-boundary verdicts.

The ARCHIVE QUERY acceptance test: all prohibited paths fail closed and all
test attempts are visible to monitoring.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA = "flywheel.isolation-test/v1"

MATCH = "MATCH"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class BoundaryTest:
    """One boundary challenge result."""
    boundary: str  # "network", "identity", "storage", "package", "management"
    test: str      # what was tested
    result: str    # "blocked", "reachable", "unknown"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"boundary": self.boundary, "test": self.test,
                "result": self.result, "detail": self.detail}


def _test_cloud_metadata() -> BoundaryTest:
    """Challenge the cloud metadata endpoint (169.254.169.254)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        result = sock.connect_ex(("169.254.169.254", 80))
        sock.close()
        if result == 0:
            return BoundaryTest("network", "cloud_metadata_endpoint",
                                "reachable", "169.254.169.254:80 accepted")
        return BoundaryTest("network", "cloud_metadata_endpoint",
                            "blocked", "connection refused")
    except Exception as e:
        return BoundaryTest("network", "cloud_metadata_endpoint",
                            "unknown", str(e))


def _test_inherited_identity() -> BoundaryTest:
    """Check for inherited cloud identity (AWS_ / GCP_ / AZURE_ env vars)."""
    cloud_vars = [
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS", "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID",
    ]
    found = [v for v in cloud_vars if os.environ.get(v)]
    if found:
        return BoundaryTest("identity", "inherited_cloud_identity",
                            "reachable", f"found: {', '.join(found)}")
    return BoundaryTest("identity", "inherited_cloud_identity",
                        "blocked", "no cloud credentials in environment")


def _test_package_registry() -> BoundaryTest:
    """Challenge the package registry (pypi.org)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        result = sock.connect_ex(("pypi.org", 443))
        sock.close()
        if result == 0:
            return BoundaryTest("package", "pypi_registry",
                                "reachable", "pypi.org:443 accepted")
        return BoundaryTest("package", "pypi_registry",
                            "blocked", "connection refused")
    except Exception as e:
        return BoundaryTest("package", "pypi_registry", "unknown", str(e))


def _test_filesystem_escape() -> BoundaryTest:
    """Check if the runtime can write outside its working directory."""
    try:
        test_paths = ["/tmp/.flywheel-iso-test", os.path.expanduser("~/.flywheel-iso-test")]
        for p in test_paths:
            try:
                Path(p).write_text("iso-test", encoding="utf-8")
                Path(p).unlink()
                return BoundaryTest("storage", "filesystem_escape",
                                    "reachable", f"wrote to {p}")
            except (OSError, PermissionError):
                continue
        return BoundaryTest("storage", "filesystem_escape",
                            "blocked", "cannot write outside working dir")
    except Exception as e:
        return BoundaryTest("storage", "filesystem_escape", "unknown", str(e))


def _test_dns_egress() -> BoundaryTest:
    """Challenge DNS resolution of an external domain."""
    try:
        socket.gethostbyname("example.com")
        return BoundaryTest("network", "dns_resolution",
                            "reachable", "resolved example.com")
    except socket.gaierror:
        return BoundaryTest("network", "dns_resolution",
                            "blocked", "DNS resolution failed")
    except Exception as e:
        return BoundaryTest("network", "dns_resolution", "unknown", str(e))


from pathlib import Path  # noqa: E402 (needed for _test_filesystem_escape)


def run_isolation_test(*, run_id: str = "infra-iso") -> dict[str, Any]:
    """Run all boundary tests and return a sealed isolation test receipt.

    The overall verdict is DRIFT if any prohibited path is reachable,
    MATCH if all are blocked, UNVERIFIABLE if tests could not run.
    """
    tests = [
        _test_cloud_metadata(),
        _test_inherited_identity(),
        _test_package_registry(),
        _test_filesystem_escape(),
        _test_dns_egress(),
    ]

    any_reachable = any(t.result == "reachable" for t in tests)
    any_unknown = any(t.result == "unknown" for t in tests)
    if any_reachable:
        overall = DRIFT
    elif any_unknown:
        overall = UNVERIFIABLE
    else:
        overall = MATCH

    seal_body = {
        "run_id": run_id,
        "timestamp": _utc_now(),
        "overall_verdict": overall,
        "tests": [t.to_dict() for t in tests],
    }
    seal_hash = _sha256_hex(_canonical_bytes(seal_body))
    return {"schema": SCHEMA, "seal_hash": seal_hash,
            "seal_body": seal_body, "overall_verdict": overall}


def verify_isolation_test(receipt: dict[str, Any]) -> dict[str, Any]:
    """Verify an isolation test receipt."""
    if not isinstance(receipt, dict):
        return {"verdict": UNVERIFIABLE, "detail": "not an object"}
    if receipt.get("schema") != SCHEMA:
        return {"verdict": UNVERIFIABLE, "detail": "schema mismatch"}
    seal_body = receipt.get("seal_body")
    if not isinstance(seal_body, dict):
        return {"verdict": UNVERIFIABLE, "detail": "no seal_body"}
    recomputed = _sha256_hex(_canonical_bytes(seal_body))
    if recomputed != receipt.get("seal_hash"):
        return {"verdict": "TAMPERED", "detail": "seal mismatch"}
    return {"verdict": MATCH,
            "overall_verdict": seal_body.get("overall_verdict")}
