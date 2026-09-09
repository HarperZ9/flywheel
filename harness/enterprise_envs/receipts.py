"""Receipt and artifact-root helpers for enterprise environments."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from harness.cross_harness_artifacts import preflight_artifact_root

from .digest import canonical_json, digest, digest_bytes

_BEARER_RE = re.compile(rb"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]*[-._~+/=][A-Za-z0-9._~+/=-]*")
_JSON_AUTH_RE = re.compile(rb"(?i)[\"']authorization[\"']\s*:\s*[\"']Bearer\s+[^\"']+[\"']")
_CONTROL_HEADER_RE = re.compile(rb"(?i)x-flywheel-control-token\s*[:=]")


class ArtifactRootRejected(ValueError):
    def __init__(self, receipt: dict[str, Any]):
        super().__init__(receipt.get("failure_code", "artifact_root_rejected"))
        self.receipt = receipt


def prepare_artifact_root(source_root: Path, artifact_root: Path, environment_id: str) -> dict[str, Any]:
    """Preflight an output root before environment artifacts are written."""

    try:
        resolved = preflight_artifact_root(Path(source_root), Path(artifact_root))
    except ValueError as exc:
        code = str(exc) or "artifact_root_rejected"
        if code not in {"artifact_root_inside_source", "artifact_root_parent_missing", "source_root_not_directory"}:
            code = "artifact_root_rejected"
        return {
            "schema": "flywheel.enterprise-environment-output-root-preflight/v1",
            "verdict": "reject",
            "failure_code": code,
            "environment_id": environment_id,
            "rejected_artifact_root_created": Path(artifact_root).exists(),
        }
    return {
        "schema": "flywheel.enterprise-environment-output-root-preflight/v1",
        "verdict": "accept",
        "environment_id": environment_id,
        "artifact_root": str(resolved),
    }


def rejected_root_receipt(preflight: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    receipt = {
        "schema": "flywheel.enterprise-environment-rejected-output-root-receipt/v1",
        "environment_id": preflight["environment_id"],
        "verdict": "reject",
        "failure_code": preflight.get("failure_code", "artifact_root_rejected"),
        "rejected_artifact_root_created": Path(artifact_root).exists(),
        "bounded_failure_surface": True,
    }
    return bind_rejection_receipt(receipt)


def bind_rejection_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    subject = {key: value for key, value in sorted(receipt.items()) if key != "rejection_receipt_sha256"}
    receipt["rejection_receipt_sha256"] = digest("flywheel.enterprise-env.rejected-output-root/v1", subject)
    return receipt


def write_json(path: Path, value: Any) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json(value).encode("utf-8") + b"\n"
    path.write_bytes(data)
    return digest_bytes(data)


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def scan_text_artifacts_for_bearer(root: Path) -> dict[str, Any]:
    return scan_text_artifacts_for_secrets(root, [])


def scan_text_artifacts_for_secrets(root: Path, secret_values: Iterable[str]) -> dict[str, Any]:
    """Scan artifacts for issued secret values and common bearer serializations.

    The result names files and detector labels only. It never returns secret values.
    """

    root = Path(root)
    secret_list = list(secret_values)
    patterns = _secret_patterns(secret_list)
    matches: dict[str, set[str]] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        data = path.read_bytes()
        labels = _classify_secret_matches(data, patterns)
        if labels:
            matches[path.relative_to(root).as_posix()] = set(labels)
    return {
        "schema": "flywheel.enterprise-environment-secret-scan/v1",
        "secret_values_present": bool(matches),
        "matching_artifacts": sorted(matches),
        "detector_labels": {name: sorted(labels) for name, labels in sorted(matches.items())},
        "checked_secret_value_count": len(secret_list),
        "raw_secret_values_returned": False,
    }


def secret_scanner_controls() -> dict[str, Any]:
    synthetic_values = ["agent_TOKEN_VALUE_FOR_SCANNER_CONTROL", "control_TOKEN_VALUE_FOR_SCANNER_CONTROL"]
    cases = {
        "issued_agent_value": synthetic_values[0].encode("utf-8"),
        "issued_control_value": synthetic_values[1].encode("utf-8"),
        "authorization_header": b"Authorization: Bearer serialized-token",
        "json_authorization_field": b'{"authorization":"Bearer serialized-token"}',
        "control_token_header": b"X-Flywheel-Control-Token: serialized-token",
    }
    patterns = _secret_patterns(synthetic_values)
    results = {case_id: bool(_classify_secret_matches(data, patterns)) for case_id, data in cases.items()}
    return {
        "schema": "flywheel.enterprise-environment-secret-scanner-controls/v1",
        "case_results": results,
        "false_negatives": sorted(case_id for case_id, passed in results.items() if not passed),
        "uses_synthetic_secret_values_only": True,
        "raw_secret_values_returned": False,
    }


def _secret_patterns(secret_values: Iterable[str]) -> list[tuple[str, bytes | re.Pattern[bytes]]]:
    patterns: list[tuple[str, bytes | re.Pattern[bytes]]] = [
        ("bearer_serialization", _BEARER_RE),
        ("json_authorization_bearer", _JSON_AUTH_RE),
        ("control_token_header", _CONTROL_HEADER_RE),
    ]
    for index, value in enumerate(secret_values):
        if value:
            patterns.append((f"issued_secret_value_{index}", value.encode("utf-8")))
    return patterns


def _classify_secret_matches(data: bytes, patterns: list[tuple[str, bytes | re.Pattern[bytes]]]) -> list[str]:
    labels: list[str] = []
    for label, pattern in patterns:
        if isinstance(pattern, bytes):
            found = pattern in data
        else:
            found = pattern.search(data) is not None
        if found:
            labels.append(label)
    return labels
