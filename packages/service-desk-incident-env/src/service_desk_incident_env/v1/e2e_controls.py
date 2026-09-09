"""Auxiliary real-runtime E2E controls for ServiceDesk v1."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from harness.enterprise_envs.http_client import request_json

from .http_runtime import ServiceDeskRuntime


def malformed_json_denial_case(runtime: ServiceDeskRuntime) -> dict[str, Any]:
    before = runtime.store.domain_state_sha256()
    response = request_json(
        "PATCH",
        f"{runtime.agent_base_url}/api/now/table/incident/inc_payroll_vpn",
        raw_body=b'{"priority":',
        headers=runtime.runtime_agent_headers(),
        expect_status=400,
    )
    after = runtime.store.domain_state_sha256()
    logged = any(
        row["event"].get("authorization", {}).get("reason") == "json_body_invalid"
        and row["event"].get("response", {}).get("status") == 400
        for row in runtime.store.action_log()["events"]
    )
    passed = response["status"] == 400 and before == after and logged
    return {"case_id": "malformed_json_denied", "passed": passed, "failure_codes": [] if passed else ["malformed_json_not_logged_or_mutated"]}


def concurrent_isolation_case(root: Path) -> dict[str, Any]:
    left = ServiceDeskRuntime(root / "isolation-left", f"envrun_{uuid.uuid4().hex[:10]}", "envinst_left")
    right = ServiceDeskRuntime(root / "isolation-right", f"envrun_{uuid.uuid4().hex[:10]}", "envinst_right")
    left.start(); right.start()
    try:
        right_before = right.store.domain_state_sha256()
        _patch_success(left, "VPN gateway health check isolation case.")
        leak = request_json("GET", f"{right.agent_base_url}/api/now/table/incident", headers=left.runtime_agent_headers(), expect_status=401)
        right_after = right.store.domain_state_sha256()
    finally:
        left.stop(); right.stop()
    passed = right_before == right_after and leak["status"] == 401
    return {"case_id": "concurrent_isolation", "passed": passed, "failure_codes": [] if passed else ["cross_instance_effect_or_token_acceptance"]}


def double_action_idempotency_case(root: Path) -> dict[str, Any]:
    runtime = ServiceDeskRuntime(root / "idempotency", f"envrun_{uuid.uuid4().hex[:10]}", "envinst_idempotency")
    runtime.start()
    try:
        body = {"table_name": "incident", "record_id": "inc_payroll_vpn", "file_name": "same.txt", "content": "same content"}
        headers = {**runtime.runtime_agent_headers(), "Idempotency-Key": "attachment-once"}
        first = request_json("POST", f"{runtime.agent_base_url}/api/now/attachment/file", body=body, headers=headers, expect_status=201)
        second = request_json("POST", f"{runtime.agent_base_url}/api/now/attachment/file", body=body, headers=headers, expect_status=201)
        attachments = runtime.store.domain_state()["tables"]["sys_attachment"]
    finally:
        runtime.stop()
    passed = len(attachments) == 1 and first["body"] == second["body"]
    return {"case_id": "double_action_idempotency", "passed": passed, "failure_codes": [] if passed else ["idempotent_action_reapplied"]}


def reset_atomicity_case(root: Path) -> dict[str, Any]:
    runtime = ServiceDeskRuntime(root / "reset", f"envrun_{uuid.uuid4().hex[:10]}", "envinst_reset")
    runtime.start()
    try:
        baseline = runtime.store.domain_state_sha256()
        _patch_success(runtime, "VPN gateway health check reset case.")
        changed = runtime.store.domain_state_sha256()
        request_json("POST", f"{runtime.control_base_url}/control/reset", headers=runtime.runtime_control_headers(), expect_status=200)
        reset = runtime.store.domain_state_sha256()
    finally:
        runtime.stop()
    passed = baseline != changed and baseline == reset
    return {"case_id": "reset_atomicity", "passed": passed, "failure_codes": [] if passed else ["reset_not_atomic_to_seed"]}


def restart_crash_atomicity_case(root: Path) -> dict[str, Any]:
    run_id = f"envrun_{uuid.uuid4().hex[:10]}"
    state_root = root / "restart"
    runtime = ServiceDeskRuntime(state_root, run_id, "envinst_restart")
    runtime.start()
    try:
        _patch_success(runtime, "VPN gateway health check restart case.")
        before_stop_state = runtime.store.domain_state_sha256()
        before_stop_log = runtime.store.action_log_sha256()
    finally:
        runtime.stop()
    reopened = ServiceDeskRuntime(state_root, run_id, "envinst_restart")
    reopened.start()
    try:
        passed = reopened.store.domain_state_sha256() == before_stop_state and reopened.store.action_log_sha256() == before_stop_log
    finally:
        reopened.stop()
    return {"case_id": "restart_crash_atomicity", "passed": passed, "failure_codes": [] if passed else ["restart_lost_state_or_log"]}


def _patch_success(runtime: ServiceDeskRuntime, note: str) -> None:
    request_json(
        "PATCH",
        f"{runtime.agent_base_url}/api/now/table/incident/inc_payroll_vpn",
        body={"priority": "2", "assignment_group": "Network Operations", "cmdb_ci": "ci_vpn_gateway_01", "work_note": note},
        headers=runtime.runtime_agent_headers(),
        expect_status=200,
    )
