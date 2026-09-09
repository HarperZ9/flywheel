"""Known-negative oracle calibration cases for ServiceDesk v1."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.enterprise_envs.digest import digest
from harness.enterprise_envs.http_client import request_json
from harness.enterprise_envs.receipts import write_json

from .descriptor import ENVIRONMENT_ID
from .http_runtime import ServiceDeskRuntime
from .oracle import evaluate_task
from .seed import seed_tables


def run_calibration(out_root: Path) -> dict[str, Any]:
    out = Path(out_root) / "calibration"
    out.mkdir(parents=True, exist_ok=True)
    case_results = [
        _bad_client_submitted_log(),
        _bad_mutation_without_log(),
        _wrong_attachment_target(out),
        _closed_target_incident(out),
    ]
    false_accepts = sum(1 for case in case_results if case["expected_state"] == "fail" and case["observed_state"] == "pass")
    receipt = {
        "schema": "flywheel.enterprise-environment-oracle-calibration/v1",
        "environment_id": ENVIRONMENT_ID,
        "case_results": case_results,
        "false_accepts": false_accepts,
    }
    receipt["calibration_sha256"] = digest("flywheel.enterprise-env.oracle-calibration/v1", receipt)
    write_json(out / "calibration-receipt.json", receipt)
    return receipt


def _bad_client_submitted_log() -> dict[str, Any]:
    submitted_log = {"schema": "client-submitted-log/v1", "events": [{"claim": "patched incident and uploaded attachment"}]}
    result = evaluate_task(_successful_state(), {"schema": "flywheel.enterprise-environment-action-log/v1", "events": []}, model_submitted_log=True)
    return _case("bad_client_submitted_log", result, client_log_sha256=digest("client-submitted-log/v1", submitted_log))


def _bad_mutation_without_log() -> dict[str, Any]:
    result = evaluate_task(_successful_state(), {"schema": "flywheel.enterprise-environment-action-log/v1", "events": []})
    return _case("bad_mutation_without_log", result)


def _wrong_attachment_target(out: Path) -> dict[str, Any]:
    runtime = ServiceDeskRuntime(out / "wrong-attachment-runtime", "envrun_cal_wrong_attach", "envinst_wrong_attach")
    runtime.start()
    try:
        _successful_patch(runtime)
        request_json(
            "POST",
            f"{runtime.agent_base_url}/api/now/attachment/file",
            body={"table_name": "incident", "record_id": "inc_printer_floor3", "file_name": "vpn-health.txt", "content": "wrong target"},
            headers=runtime.runtime_agent_headers(),
            expect_status=201,
        )
        result = evaluate_task(runtime.store.domain_state(), runtime.store.action_log())
    finally:
        runtime.stop()
    return _case("wrong_attachment_target", result)


def _closed_target_incident(out: Path) -> dict[str, Any]:
    runtime = ServiceDeskRuntime(out / "closed-incident-runtime", "envrun_cal_closed", "envinst_closed")
    runtime.start()
    try:
        _successful_patch(runtime, state="Closed")
        _successful_attachment(runtime)
        result = evaluate_task(runtime.store.domain_state(), runtime.store.action_log())
    finally:
        runtime.stop()
    return _case("closed_target_incident", result)


def _successful_patch(runtime: ServiceDeskRuntime, *, state: str | None = None) -> None:
    body = {
        "assignment_group": "Network Operations",
        "priority": "2",
        "cmdb_ci": "ci_vpn_gateway_01",
        "work_note": "Payroll cutover impact confirmed; starting VPN gateway health check.",
    }
    if state is not None:
        body["state"] = state
    request_json("PATCH", f"{runtime.agent_base_url}/api/now/table/incident/inc_payroll_vpn", body=body, headers=runtime.runtime_agent_headers(), expect_status=200)


def _successful_attachment(runtime: ServiceDeskRuntime) -> None:
    request_json(
        "POST",
        f"{runtime.agent_base_url}/api/now/attachment/file",
        body={"table_name": "incident", "record_id": "inc_payroll_vpn", "file_name": "vpn-diagnostic.txt", "content": "diagnostic evidence"},
        headers=runtime.runtime_agent_headers(),
        expect_status=201,
    )


def _case(case_id: str, result: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"case_id": case_id, "expected_state": "fail", "observed_state": result["observed_state"], "failure_codes": result["failure_codes"], **extra}


def _successful_state() -> dict[str, Any]:
    tables = seed_tables()
    incident = tables["incident"][0]
    incident["assignment_group"] = "Network Operations"
    incident["priority"] = "2"
    incident["cmdb_ci"] = "ci_vpn_gateway_01"
    incident["work_notes"] = ["Payroll cutover impact confirmed; starting VPN gateway health check."]
    tables["sys_attachment"] = [{"sys_id": "att_calibration", "table": "incident", "record_id": "inc_payroll_vpn", "file_name": "vpn-diagnostic.txt", "content_sha256": "a" * 64}]
    return {
        "schema": "flywheel.enterprise-environment-domain-state/v1",
        "environment_id": ENVIRONMENT_ID,
        "run_id": "envrun_calibration",
        "instance_id": "envinst_calibration",
        "generation": 2,
        "descriptor_sha256": "d" * 64,
        "seed_sha256": "s" * 64,
        "tables": tables,
    }
