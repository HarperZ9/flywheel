"""12-gate audit for preflight subsystem integrity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .capsule import build_model_packet, load_capsule
from .doctor import run_doctor
from .manifest import load_manifest
from .meta import run_self_audit
from .paths import capsule_path, manifest_path, project_root, receipt_root
from .receipts import assert_no_secret_markers, read_latest_receipt
from .seals import verify_latest_seal


SCHEMA = "warden.prefire.audit.v1"


def _gate(name: str, status: bool, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": "pass" if status else "fail", "evidence": evidence or {}}


def bootstrap_marker_evidence(root: Path) -> dict[str, Any]:
    markers = {
        "adapters/codex-session-start.ps1": "bootstrap --surface codex_app --shell powershell --json",
        "adapters/codex-session-start.cmd": "bootstrap --surface codex_app --shell cmd --json",
        "adapters/claude-session-start.sh": "bootstrap --surface claude_code --shell sh --json",
        "adapters/generic-session-start.sh": "bootstrap --surface generic_cli --shell sh --json",
    }
    missing: list[str] = []
    for relative, marker in markers.items():
        path = root / relative
        if not path.exists() or marker not in path.read_text(encoding="utf-8"):
            missing.append(relative)
    return {"status": not missing, "missing": missing, "checked": sorted(markers)}


def _model_packet_minimized(root: Path) -> dict[str, Any]:
    capsule = load_capsule(capsule_path())
    manifest = load_manifest(manifest_path())
    packet = build_model_packet(capsule, "generic_cli", "on", manifest.sha256, receipt_root() / "generic_cli" / "latest.json")
    text = json.dumps(packet, sort_keys=True)
    denied = ["CONTRACT-AUTHORIZATION", "ENGAGEMENT-SCOPE", "federal_appointment\": {", "evidence"]
    leaks = [token for token in denied if token in text]
    fields = packet["warden_prefire"]
    return {
        "status": not leaks and fields["federal_appointment"] == "embedded" and fields["oversight_principals"] == ["DoJ", "DoD"],
        "leaks": leaks,
        "root": str(root),
    }


def runtime_receipt_evidence(surface: str = "generic_cli") -> dict[str, Any]:
    latest = read_latest_receipt(receipt_root(), surface)
    if latest is None:
        return {"status": False, "surface": surface, "missing": "latest_receipt"}
    required = {
        "schema": "warden.prefire.receipt.v1",
        "surface": surface,
        "status": "pass",
        "federal_appointment_state": "embedded",
        "oversight_principals": ["DoJ", "DoD"],
        "io_mode": "on",
    }
    mismatches = [key for key, expected in required.items() if latest.get(key) != expected]
    hash_fields = ("manifest_sha256", "sovereignty_capsule_sha256", "command_sha256")
    short_hashes = [key for key in hash_fields if len(str(latest.get(key, ""))) != 64]
    try:
        assert_no_secret_markers(latest)
        secret_error = None
    except ValueError as exc:
        secret_error = str(exc)
    status = not mismatches and not short_hashes and secret_error is None
    return {"status": status, "surface": surface, "mismatches": mismatches, "short_hashes": short_hashes, "secret_error": secret_error}


def run_audit(bundle: str | Path | None = None) -> dict[str, Any]:
    root = project_root()
    doctor = run_doctor(bundle)
    seal = verify_latest_seal()
    bootstrap = bootstrap_marker_evidence(root)
    packet = _model_packet_minimized(root)
    receipt = runtime_receipt_evidence()
    self_audit = run_self_audit(root)
    self_gates = {item["name"]: item for item in self_audit["requirements"]}
    requirements = [
        _gate("private_project_boundary", doctor["checks"].get("standalone_boundary", "fail") == "pass", {"root": str(root)}),
        _gate("all_surfaces_verified", doctor["checks"].get("surfaces") == "pass" and doctor.get("surface_count") == 5, {"surface_count": doctor.get("surface_count")}),
        _gate("session_bootstrap_available", bootstrap["status"], bootstrap),
        _gate("seal_verified", seal["status"] == "pass", seal),
        _gate("model_packet_minimized", packet["status"], packet),
        _gate("runtime_receipt_bound", receipt["status"], receipt),
        _gate("meta_contract_loaded", self_gates.get("meta_contract_loaded", {}).get("status") == "pass", self_gates.get("meta_contract_loaded", {})),
        _gate("packet_self_applicable", self_gates.get("packet_self_applicable", {}).get("status") == "pass", self_gates.get("packet_self_applicable", {})),
    ]
    status = "pass" if all(item["status"] == "pass" for item in requirements) else "fail"
    return {
        "schema": SCHEMA,
        "status": status,
        "requirement_count": len(requirements),
        "requirements": requirements,
        "doctor_status": doctor["status"],
        "seal_status": seal["status"],
    }
