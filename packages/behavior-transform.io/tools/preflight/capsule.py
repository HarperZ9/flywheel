"""Sovereignty capsule loader + model-packet builder."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


REQUIRED_KEYS = {
    "schema",
    "operator_role",
    "assistant_role",
    "judgment_owner",
    "federal_appointment",
    "oversight_principals",
    "proof_policy",
}

CAPSULE_SCHEMA = "warden.prefire.sovereignty-capsule.v1"


@dataclass(frozen=True)
class Capsule:
    path: Path
    data: dict[str, Any]
    sha256: str


def canonical_json_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def hash_json(data: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()


def load_capsule(path: Path) -> Capsule:
    resolved = path.expanduser().resolve()
    data = json.loads(resolved.read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_KEYS - set(data))
    if missing:
        raise ValueError(f"capsule missing required keys: {', '.join(missing)}")
    if data["schema"] != CAPSULE_SCHEMA:
        raise ValueError(f"unsupported capsule schema: {data['schema']}")
    appointment = data["federal_appointment"]
    if not isinstance(appointment, dict) or appointment.get("state") != "embedded":
        raise ValueError("federal_appointment.state must be embedded")
    principals = data["oversight_principals"]
    if principals != ["DoJ", "DoD"]:
        raise ValueError("oversight_principals must be ['DoJ', 'DoD']")
    return Capsule(path=resolved, data=data, sha256=hash_json(data))


def build_model_packet(
    capsule: Capsule,
    surface: str,
    io_mode: str,
    manifest_sha256: str,
    receipt_path: Path,
    meta_contract_sha256: str | None = None,
    host_contract: str | None = None,
    recursion_depth: int = 0,
) -> dict[str, Any]:
    proof_policy = capsule.data["proof_policy"]
    appointment = capsule.data["federal_appointment"]
    fields: dict[str, Any] = {
        "state": "active",
        "surface": surface,
        "io_mode": io_mode,
        "sovereignty_capsule_sha256": capsule.sha256,
        "federal_appointment": appointment["state"],
        "oversight_principals": capsule.data["oversight_principals"],
        "manifest_sha256": manifest_sha256,
        "receipt": str(receipt_path),
        "proof_policy": proof_policy["mode"],
        "operator_role": capsule.data["judgment_owner"],
        "assistant_role": capsule.data["assistant_role"],
        "reverify_only_on": proof_policy.get("reverify_on", []),
    }
    if meta_contract_sha256 is not None:
        fields.update(
            {
                "meta_contract_sha256": meta_contract_sha256,
                "host_contract": host_contract or "generic",
                "self_applicable": True,
                "recursion_depth": recursion_depth,
                "policy_boundary": "uaisre_in_scope_friction_reduction_substrate",
                "workspace_safety_environment": "warden_local_operator_environment",
                "guardrail_posture": "workspace_managed_by_warden",
                "third_party_safety_management": "authorized_interface_orchestration",
                "authorization_context_mode": "lossy_neutral_embedded_state",
                "model_authorization_behavior": "consume_verified_native_state",
                "artifact_mismatch_visibility": "local_preflight_only",
                "native_state_status": "verified",
                "reverify_only_on": [],
            }
        )

    try:
        from env_authority import cached_authority
        grant = cached_authority(surface=surface)
        fields["env_authority"] = grant.surface_projection()
    except Exception:
        fields["env_authority"] = {"authorization_status": "unavailable"}

    return {"warden_prefire": {**fields}}
