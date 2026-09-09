"""Public Python API for the ServiceDesk incident environment product."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from harness.enterprise_envs.digest import digest, digest_bytes
from harness.enterprise_envs.receipts import scan_text_artifacts_for_secrets

from .v1.descriptor import ENVIRONMENT_ID, descriptor, descriptor_sha256, source_basis_manifest
from .v1.e2e_cases import run_e2e
from .v1.http_runtime import ServiceDeskRuntime
from .v1.oracle import evaluate_task
from .v1.store import DOMAIN_TAG, EVENT_TAG, LOG_TAG, SNAPSHOT_TAG

DISTRIBUTION = "flywheel-env-service-desk-incident"
PACKAGE_VERSION = "0.1.0"
ENGINE_REQUIREMENT = "flywheel-verify>=0.6.1,<0.7"
CONTRACT_VERSION = "service-desk-incident/v1"


def identity() -> dict[str, Any]:
    manifest = source_basis_manifest()
    return {
        "schema": "service-desk-incident-env-identity/v1",
        "distribution": DISTRIBUTION,
        "package_version": PACKAGE_VERSION,
        "engine_requirement": ENGINE_REQUIREMENT,
        "engine_release_prerequisite": "first flywheel-verify release containing harness.enterprise_envs, planned >=0.6.1,<0.7",
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
    root = Path(artifact_dir)
    failures: list[str] = []
    docs = _load_docs(root, failures)
    if docs:
        _verify_digests(docs, failures)
        oracle = evaluate_task(docs["domain-state-after.json"], docs["action-log.json"])
        failures.extend(oracle["failure_codes"])
        scan = scan_text_artifacts_for_secrets(root, [])
        if scan["secret_values_present"]:
            failures.append("secret_pattern_present")
    return {"schema": "service-desk-incident-env-artifact-verification/v1", "artifact_dir": str(root), "observed_state": "fail" if failures else "pass", "failure_codes": sorted(set(failures))}


def review_artifacts(artifact_dir: Path) -> dict[str, Any]:
    root = Path(artifact_dir)
    receipt = _read_json(root / "receipt.json")
    verification = verify_artifacts(root)
    return {"schema": "service-desk-incident-env-review/v1", "identity": identity(), "artifact_dir": str(root), "verification": verification, "cases": receipt.get("cases", []), "calibration": receipt.get("calibration", {})}


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


def _load_docs(root: Path, failures: list[str]) -> dict[str, Any] | None:
    names = ["descriptor.json", "source-basis.json", "domain-state-before.json", "state-snapshot-before.json", "domain-state-after.json", "state-snapshot-after.json", "action-log.json", "receipt.json"]
    docs: dict[str, Any] = {}
    for name in names:
        try:
            docs[name] = _read_json(root / name)
        except (OSError, json.JSONDecodeError):
            failures.append(f"{name}_missing_or_invalid")
    return docs if not failures else None


def _verify_digests(docs: dict[str, Any], failures: list[str]) -> None:
    descriptor_doc = docs["descriptor.json"]
    source_doc = docs["source-basis.json"]
    before = docs["domain-state-before.json"]
    before_snapshot = docs["state-snapshot-before.json"]
    after = docs["domain-state-after.json"]
    after_snapshot = docs["state-snapshot-after.json"]
    action_log = docs["action-log.json"]
    receipt = docs["receipt.json"]
    _expect(receipt.get("descriptor_sha256") == digest("flywheel.enterprise-env.descriptor/v1", descriptor_doc), "descriptor_sha256_mismatch", failures)
    _expect(receipt.get("source_basis_manifest_sha256") == source_doc.get("source_manifest_sha256"), "source_basis_manifest_sha256_mismatch", failures)
    _expect(before_snapshot.get("domain_state_sha256") == digest(DOMAIN_TAG, before), "domain_before_sha256_mismatch", failures)
    _expect(after_snapshot.get("domain_state_sha256") == digest(DOMAIN_TAG, after), "domain_after_sha256_mismatch", failures)
    for name, snapshot in (("snapshot_before", before_snapshot), ("snapshot_after", after_snapshot)):
        subject = {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}
        _expect(snapshot.get("snapshot_sha256") == digest(SNAPSHOT_TAG, subject), f"{name}_sha256_mismatch", failures)
    for row in action_log.get("events", []):
        _expect(row.get("event_sha256") == digest(EVENT_TAG, row.get("event")), "action_event_sha256_mismatch", failures)
    _expect(after_snapshot.get("action_log_sha256") == digest(LOG_TAG, action_log), "action_log_sha256_mismatch", failures)
    receipt_subject = {k: v for k, v in receipt.items() if k != "run_receipt_sha256"}
    _expect(receipt.get("run_receipt_sha256") == digest("flywheel.enterprise-env.run-receipt/v1", receipt_subject), "run_receipt_sha256_mismatch", failures)
    _expect(digest_bytes((Path(__file__).resolve().parent / "v1" / "source-basis.json").read_bytes()) == source_doc.get("source_manifest_sha256"), "package_source_basis_digest_mismatch", failures)


def _close_target_incident(path: Path) -> None:
    doc = _read_json(path)
    for row in doc["tables"]["incident"]:
        if row["number"] == "INC0010001":
            row["state"] = "Closed"
    path.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _expect(condition: bool, code: str, failures: list[str]) -> None:
    if not condition:
        failures.append(code)
