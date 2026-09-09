"""Descriptor validation for independently versioned enterprise environments."""
from __future__ import annotations

import re
from typing import Any

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def validate_descriptor(doc: dict[str, Any]) -> dict[str, Any]:
    """Validate the portable environment descriptor contract used by v1 packages."""

    _require(isinstance(doc, dict), "descriptor_not_object")
    _require(doc.get("schema") == "flywheel.enterprise-environment-descriptor/v1", "descriptor_schema_invalid")
    environment_id = doc.get("environment_id")
    _require(isinstance(environment_id, str) and environment_id.endswith("/v1"), "environment_id_invalid")
    _require(isinstance(doc.get("package"), str) and doc["package"], "package_missing")
    authority = doc.get("authority")
    _require(isinstance(authority, dict), "authority_missing")
    _require(authority.get("hidden_control_required") is True, "hidden_control_required_missing")
    _require(authority.get("separate_ports_required") is True, "separate_ports_required_missing")
    source_basis = doc.get("source_basis")
    _require(isinstance(source_basis, list) and source_basis, "source_basis_missing")
    for index, row in enumerate(source_basis):
        prefix = f"source_basis[{index}]"
        _require(isinstance(row, dict), f"{prefix}_not_object")
        _require(isinstance(row.get("source_artifact_ref"), str) and row["source_artifact_ref"], f"{prefix}_artifact_ref_missing")
        _require(isinstance(row.get("source_manifest_sha256"), str) and _SHA256_RE.match(row["source_manifest_sha256"]) is not None, f"{prefix}_manifest_sha_invalid")
        _require(isinstance(row.get("source_sha256"), str) and _SHA256_RE.match(row["source_sha256"]) is not None, f"{prefix}_source_sha_invalid")
        _require(isinstance(row.get("retrieved_at_utc"), str) and row["retrieved_at_utc"].endswith("Z"), f"{prefix}_retrieved_at_invalid")
        _require(isinstance(row.get("used_for"), list) and row["used_for"], f"{prefix}_used_for_missing")
    return doc
