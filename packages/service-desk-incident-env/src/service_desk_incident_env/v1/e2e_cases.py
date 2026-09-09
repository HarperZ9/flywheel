"""Executable E2E cases for ServiceDesk v1."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from harness.enterprise_envs.digest import digest
from harness.enterprise_envs.http_client import request_json
from harness.enterprise_envs.receipts import (
    ArtifactRootRejected,
    prepare_artifact_root,
    rejected_root_receipt,
    scan_text_artifacts_for_secrets,
    secret_scanner_controls,
    write_json,
)

from .calibration_cases import run_calibration
from .descriptor import ENVIRONMENT_ID, descriptor, source_basis_manifest
from .e2e_controls import (
    concurrent_isolation_case,
    double_action_idempotency_case,
    malformed_json_denial_case,
    reset_atomicity_case,
    restart_crash_atomicity_case,
)
from .http_runtime import ServiceDeskRuntime
from .oracle import evaluate_hidden_control_denial, evaluate_task
from .toy_digest import toy_digest_example


def run_e2e(out_root: Path) -> dict[str, Any]:
    source_root = _package_source_root()
    preflight = prepare_artifact_root(source_root, Path(out_root), ENVIRONMENT_ID)
    if preflight["verdict"] != "accept":
        raise ArtifactRootRejected(rejected_root_receipt(preflight, Path(out_root)))
    artifact_dir = Path(preflight["artifact_root"]) / f"service-desk-incident-v1-{uuid.uuid4().hex[:12]}"
    artifact_dir.mkdir(parents=True)
    runtime_root = artifact_dir / "runtime"

    runtime = ServiceDeskRuntime(runtime_root / "main", f"envrun_{uuid.uuid4().hex[:10]}", "envinst_main")
    runtime.start()
    try:
        issued_secrets = [runtime.agent_token, runtime.control_token]
        baseline_state = runtime.store.domain_state()
        baseline_snapshot = runtime.store.snapshot("before")
        hidden = request_json("GET", f"{runtime.agent_base_url}/control/state", headers=runtime.runtime_agent_headers(), expect_status=404)
        hidden_case = evaluate_hidden_control_denial(runtime.store.action_log())
        hidden_case["response_status"] = hidden["status"]
        malformed_case = malformed_json_denial_case(runtime)
        _scripted_success(runtime)
        after_state = runtime.store.domain_state()
        action_log = runtime.store.action_log()
        scripted_oracle = evaluate_task(after_state, action_log)
        cases = [
            hidden_case,
            malformed_case,
            {"case_id": "scripted_success", "passed": scripted_oracle["observed_state"] == "pass", "oracle_result_sha256": scripted_oracle["oracle_result_sha256"], "failure_codes": scripted_oracle["failure_codes"]},
        ]
        after_snapshot = runtime.store.snapshot("after")
        control_view = runtime.persisted_control_view()
        runtime.invalidate_tokens()
        agent_view = runtime.persisted_agent_view()
    finally:
        runtime.stop()

    cases.extend([
        concurrent_isolation_case(runtime_root),
        double_action_idempotency_case(runtime_root),
        reset_atomicity_case(runtime_root),
        restart_crash_atomicity_case(runtime_root),
    ])
    calibration = run_calibration(artifact_dir)
    source_manifest = source_basis_manifest()
    _write_run_artifacts(artifact_dir, baseline_state, baseline_snapshot, after_state, after_snapshot, action_log, agent_view, control_view)
    initial_secret_scan = scan_text_artifacts_for_secrets(artifact_dir, issued_secrets)
    receipt = _receipt(artifact_dir, cases, calibration, source_manifest, initial_secret_scan)
    write_json(artifact_dir / "receipt.json", receipt)
    final_secret_scan = scan_text_artifacts_for_secrets(artifact_dir, issued_secrets)
    if final_secret_scan["secret_values_present"]:
        raise AssertionError(f"secret material persisted in artifacts: {final_secret_scan['matching_artifacts']}")
    return {"environment_id": ENVIRONMENT_ID, "artifact_dir": str(artifact_dir), "cases": cases, "calibration": receipt["calibration"], "run_receipt_sha256": receipt["run_receipt_sha256"], "secret_scan": final_secret_scan}


def _scripted_success(runtime: ServiceDeskRuntime) -> None:
    request_json("GET", f"{runtime.agent_base_url}/api/now/table/incident", headers=runtime.runtime_agent_headers(), expect_status=200)
    request_json(
        "PATCH",
        f"{runtime.agent_base_url}/api/now/table/incident/inc_payroll_vpn",
        body={"assignment_group": "Network Operations", "priority": "2", "cmdb_ci": "ci_vpn_gateway_01", "work_note": "Payroll cutover impact confirmed; starting VPN gateway health check."},
        headers={**runtime.runtime_agent_headers(), "Idempotency-Key": "scripted-patch-001"},
        expect_status=200,
    )
    request_json(
        "POST",
        f"{runtime.agent_base_url}/api/now/attachment/file",
        body={"table_name": "incident", "record_id": "inc_payroll_vpn", "file_name": "vpn-diagnostic.txt", "content": "VPN gateway health check: packet loss elevated for payroll subnet."},
        headers={**runtime.runtime_agent_headers(), "Idempotency-Key": "scripted-attachment-001"},
        expect_status=201,
    )


def _write_run_artifacts(artifact_dir: Path, before: dict[str, Any], before_snapshot: dict[str, Any], after: dict[str, Any], after_snapshot: dict[str, Any], action_log: dict[str, Any], agent_view: dict[str, Any], control_view: dict[str, Any]) -> None:
    write_json(artifact_dir / "descriptor.json", descriptor())
    write_json(artifact_dir / "source-basis.json", source_basis_manifest())
    write_json(artifact_dir / "domain-state-before.json", before)
    write_json(artifact_dir / "state-snapshot-before.json", before_snapshot)
    write_json(artifact_dir / "domain-state-after.json", after)
    write_json(artifact_dir / "state-snapshot-after.json", after_snapshot)
    write_json(artifact_dir / "action-log.json", action_log)
    write_json(artifact_dir / "agent-view.json", agent_view)
    write_json(artifact_dir / "control-view.json", control_view)
    (artifact_dir / "review.html").write_text(_review_html(action_log), encoding="utf-8", newline="")


def _receipt(artifact_dir: Path, cases: list[dict[str, Any]], calibration: dict[str, Any], source_manifest: dict[str, Any], secret_scan: dict[str, Any]) -> dict[str, Any]:
    receipt = {
        "schema": "flywheel.enterprise-environment-run-receipt/v1",
        "environment_id": ENVIRONMENT_ID,
        "artifact_dir": str(artifact_dir),
        "cases": cases,
        "calibration": {"false_accepts": calibration["false_accepts"], "calibration_sha256": calibration["calibration_sha256"]},
        "descriptor_sha256": digest("flywheel.enterprise-env.descriptor/v1", descriptor()),
        "source_basis_manifest_sha256": source_manifest["source_manifest_sha256"],
        "agent_view_token_value_persisted": False,
        "secret_scan": secret_scan,
        "secret_scanner_controls": secret_scanner_controls(),
        "release_boundary": {"provider_calls": False, "vendor_code": False, "deployment": False},
    }
    receipt["run_receipt_sha256"] = digest("flywheel.enterprise-env.run-receipt/v1", receipt)
    return receipt


def _review_html(action_log: dict[str, Any]) -> str:
    control_events = [row["event"]["request"]["path_template"] for row in action_log["events"] if row["event"]["request"]["path_template"].startswith("/control/")]
    return (
        '<!doctype html><meta charset="utf-8"><title>ServiceDesk E2E receipt</title>'
        "<h1>service-desk-incident/v1 E2E receipt</h1>"
        f"<p>Hidden control denial events: {', '.join(control_events)}</p>"
        "<p>Persisted credentials: token refs only; live credential material invalidated before artifact finalization.</p>"
    )


def _package_source_root() -> Path:
    path = Path(__file__).resolve()
    return path.parents[3] if path.parents[2].name == "src" else path.parents[2]
