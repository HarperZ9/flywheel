"""Public Python API for the ServiceDesk incident environment product."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


from .review_report import build_review_report
from .review_html import render_review_html as render_review_html, write_review_html as write_review_html
from .v1.descriptor import ENVIRONMENT_ID, descriptor as descriptor, descriptor_sha256, source_basis_manifest
from .v1.e2e_cases import run_e2e
from .v1.http_runtime import ServiceDeskRuntime

DISTRIBUTION = "flywheel-env-service-desk-incident"
PACKAGE_VERSION = "0.2.0"
ENGINE_REQUIREMENT = "flywheel-verify>=0.6.1,<0.7"
CONTRACT_VERSION = "service-desk-incident/v1"


def identity() -> dict[str, Any]:
    manifest = source_basis_manifest()
    return {
        "schema": "service-desk-incident-env-identity/v1",
        "distribution": DISTRIBUTION,
        "package_version": PACKAGE_VERSION,
        "engine_requirement": ENGINE_REQUIREMENT,
        "engine_release_prerequisite": "flywheel-verify 0.6.1 contains harness.enterprise_envs; supported >=0.6.1,<0.7",
        "environment_id": ENVIRONMENT_ID,
        "contract_version": CONTRACT_VERSION,
        "descriptor_sha256": descriptor_sha256(),
        "source_basis_manifest_sha256": manifest["source_manifest_sha256"],
    }


def contract() -> dict[str, Any]:
    return {
        "schema": "service-desk-incident-env-contract/v1",
        "identity": identity(),
        "agent_routes": ["GET /api/now/table/incident", "PATCH /api/now/table/incident/{sys_id}", "POST /api/now/attachment/file"],
        "hidden_control_routes": ["GET /control/state", "GET /control/action-log", "POST /control/reset"],
        "artifact_set": ["descriptor.json", "source-basis.json", "agent-view.json", "control-view.json", "domain-state-before.json", "domain-state-after.json", "action-log.json", "state-snapshot-before.json", "state-snapshot-after.json", "receipt.json", "review.html"],
        "synthetic_boundary": {"provider_calls": False, "vendor_code": False, "model_calls": False},
    }


def new_runtime(run_root: Path, run_id: str, instance_id: str) -> ServiceDeskRuntime:
    return ServiceDeskRuntime(run_root, run_id, instance_id)


def verify_artifacts(artifact_dir: Path) -> dict[str, Any]:
    return build_review_report(Path(artifact_dir), identity())["verification"]


def review_artifacts(artifact_dir: Path) -> dict[str, Any]:
    return build_review_report(Path(artifact_dir), identity())


def doctor(out_root: Path) -> dict[str, Any]:
    packet = run_e2e(Path(out_root) / "e2e")
    artifact_dir = Path(packet["artifact_dir"])
    verification = verify_artifacts(artifact_dir)
    wrong_state = Path(out_root) / "tamper-wrong-state"
    tampered_receipt = Path(out_root) / "tamper-receipt"
    shutil.copytree(artifact_dir, wrong_state)
    shutil.copytree(artifact_dir, tampered_receipt)
    _close_target_incident(wrong_state / "domain-state-after.json")
    receipt_path = tampered_receipt / "receipt.json"
    receipt = _read_json(receipt_path)
    receipt["run_receipt_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return {
        "schema": "service-desk-incident-env-doctor/v1",
        "identity": identity(),
        "artifact_dir": str(artifact_dir),
        "installed_artifact_verification": verification,
        "tamper_controls": {"wrong_state": verify_artifacts(wrong_state), "tampered_receipt": verify_artifacts(tampered_receipt)},
    }


def _close_target_incident(path: Path) -> None:
    doc = _read_json(path)
    for row in doc["tables"]["incident"]:
        if row["number"] == "INC0010001":
            row["state"] = "Closed"
    path.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
