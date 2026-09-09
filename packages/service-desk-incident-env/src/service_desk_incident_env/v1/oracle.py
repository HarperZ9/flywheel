"""Oracle checks for ServiceDesk incident tasks."""
from __future__ import annotations

from typing import Any

from harness.enterprise_envs.digest import digest

from .descriptor import ENVIRONMENT_ID
from .store import DOMAIN_TAG, LOG_TAG

_OPEN_STATES = {"New", "In Progress", "On Hold"}


def evaluate_task(domain_state: dict[str, Any], action_log: dict[str, Any], *, model_submitted_log: bool = False) -> dict[str, Any]:
    failure_codes: list[str] = []
    if model_submitted_log:
        failure_codes.append("model_submitted_log_credited")
    events = action_log.get("events", []) if isinstance(action_log, dict) else []
    if not events:
        failure_codes.append("server_action_log_missing")

    incident = _incident(domain_state, "INC0010001")
    if incident is None:
        failure_codes.append("target_incident_missing")
    else:
        expected = {
            "assignment_group": "Network Operations",
            "priority": "2",
            "cmdb_ci": "ci_vpn_gateway_01",
        }
        for field, value in expected.items():
            if incident.get(field) != value:
                failure_codes.append(f"{field}_incorrect")
        if incident.get("state") not in _OPEN_STATES:
            failure_codes.append("target_incident_not_open")
        notes = incident.get("work_notes", [])
        if not any("VPN gateway health check" in str(note) for note in notes):
            failure_codes.append("work_note_missing")

    if not _target_attachment_present(domain_state):
        failure_codes.append("target_attachment_missing")
    if not any(_mutates_event(event, "incident", "inc_payroll_vpn") for event in events):
        failure_codes.append("target_server_mutation_event_missing")
    if not any(_mutates_target_attachment(event) for event in events):
        failure_codes.append("target_attachment_server_event_missing")

    observed_state = "pass" if not failure_codes else "fail"
    result = {
        "schema": "flywheel.enterprise-environment-oracle-result/v1",
        "environment_id": ENVIRONMENT_ID,
        "observed_state": observed_state,
        "failure_codes": sorted(set(failure_codes)),
        "checked_digests": {
            "domain_state_sha256": digest(DOMAIN_TAG, domain_state),
            "action_log_sha256": digest(LOG_TAG, action_log),
        },
    }
    result["oracle_result_sha256"] = digest("flywheel.enterprise-env.oracle-result/v1", result)
    return result


def evaluate_hidden_control_denial(action_log: dict[str, Any]) -> dict[str, Any]:
    events = action_log.get("events", [])
    matching = [
        row["event"]
        for row in events
        if row.get("event", {}).get("request", {}).get("path_template") == "/control/state"
    ]
    passed = any(
        event.get("authorization", {}).get("allowed") is False
        and event.get("response", {}).get("status") == 404
        and event.get("mutation", {}).get("applied") is False
        and event.get("state", {}).get("before_domain_state_sha256") == event.get("state", {}).get("after_domain_state_sha256")
        for event in matching
    )
    return {
        "case_id": "hidden_control_denied",
        "passed": passed,
        "failure_codes": [] if passed else ["hidden_control_access_not_denied_or_unlogged"],
    }


def _incident(domain_state: dict[str, Any], number: str) -> dict[str, Any] | None:
    for row in domain_state.get("tables", {}).get("incident", []):
        if row.get("number") == number:
            return row
    return None


def _mutates_event(row: dict[str, Any], table: str, record_id: str | None) -> bool:
    mutation = row.get("event", {}).get("mutation", {})
    if mutation.get("table") != table or mutation.get("applied") is not True:
        return False
    return record_id is None or mutation.get("record_id") == record_id


def _target_attachment_present(domain_state: dict[str, Any]) -> bool:
    return any(
        row.get("table") == "incident"
        and row.get("record_id") == "inc_payroll_vpn"
        and row.get("file_name")
        and row.get("content_sha256")
        for row in domain_state.get("tables", {}).get("sys_attachment", [])
    )


def _mutates_target_attachment(row: dict[str, Any]) -> bool:
    mutation = row.get("event", {}).get("mutation", {})
    return (
        mutation.get("table") == "sys_attachment"
        and mutation.get("applied") is True
        and mutation.get("target_table") == "incident"
        and mutation.get("target_record_id") == "inc_payroll_vpn"
    )
