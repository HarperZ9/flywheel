"""Descriptor for the synthetic ServiceDesk incident environment."""
from __future__ import annotations

import json
from importlib import resources
from typing import Any

from harness.enterprise_envs.digest import digest, digest_bytes
from harness.enterprise_envs.descriptors import validate_descriptor

ENVIRONMENT_ID = "service-desk-incident/v1"
PACKAGE = "service_desk_incident_env.v1"
SOURCE_BASIS_PATH = "service_desk_incident_env/v1/source-basis.json"


def source_basis_manifest() -> dict[str, Any]:
    data = resources.files(__package__).joinpath("source-basis.json").read_bytes()
    manifest = json.loads(data.decode("utf-8"))
    manifest["source_manifest_sha256"] = digest_bytes(data)
    return manifest


def descriptor() -> dict[str, Any]:
    manifest = source_basis_manifest()
    manifest_sha = manifest["source_manifest_sha256"]
    source_basis = []
    for entry in manifest["entries"]:
        source_basis.append(
            {
                "id": entry["id"],
                "url": entry["url"],
                "source_artifact_ref": f"{SOURCE_BASIS_PATH}#/entries/{entry['id']}",
                "source_manifest_sha256": manifest_sha,
                "source_sha256": entry["body_sha256"],
                "retrieved_at_utc": entry["retrieved_at_utc"],
                "used_for": entry["used_for"],
            }
        )
    doc = {
        "schema": "flywheel.enterprise-environment-descriptor/v1",
        "environment_id": ENVIRONMENT_ID,
        "package": PACKAGE,
        "display_name": "Synthetic ServiceDesk incident workflow",
        "version": "1.0.0",
        "domain": "enterprise-service-management",
        "synthetic_boundary": {
            "uses_live_vendor": False,
            "source_family": "ServiceNow-like documented subset",
            "provider_calls_allowed": False,
        },
        "entrypoints": {
            "cli": "python -m harness.enterprise_envs.cli e2e service-desk-incident/v1 --out <artifact-root>",
            "agent_api": "runtime loopback HTTP table and attachment subset",
            "control_api": "runtime loopback HTTP hidden control subset",
        },
        "authority": {
            "hidden_control_required": True,
            "separate_ports_required": True,
            "agent_can_read_control": False,
            "agent_token_persisted": False,
        },
        "source_basis": source_basis,
        "release_boundary": {
            "scope": "first independently versioned enterprise environment package",
            "not_scope_ceiling": True,
            "no_provider_calls": True,
        },
    }
    validate_descriptor(doc)
    return doc


def descriptor_sha256() -> str:
    return digest("flywheel.enterprise-env.descriptor/v1", descriptor())
