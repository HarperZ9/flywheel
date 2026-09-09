"""Contract-fixed toy digest fixture for ServiceDesk v1."""
from __future__ import annotations

from typing import Any

from harness.enterprise_envs.digest import digest, preimage

from .descriptor import ENVIRONMENT_ID
from .store import DOMAIN_TAG, EVENT_TAG, LOG_TAG, SNAPSHOT_TAG


def toy_digest_example() -> dict[str, Any]:
    desc = "d" * 64
    seed = "s" * 64
    base_meta = {
        "environment_id": ENVIRONMENT_ID,
        "run_id": "envrun_toy",
        "instance_id": "envinst_toy_a",
        "generation": 0,
        "descriptor_sha256": desc,
        "seed_sha256": seed,
        "state_schema": "flywheel.enterprise-environment-domain-state/v1",
    }
    before_state = {
        **base_meta,
        "tables": {
            "cmdb_ci": [{"sys_id": "ci_vpn_gateway_01", "name": "vpn-gateway-01"}],
            "incident": [{"sys_id": "inc_payroll_vpn", "number": "INC0010001", "short_description": "Payroll users cannot reach VPN", "assignment_group": "Help Desk", "priority": "4", "state": "New", "cmdb_ci": "", "work_notes": []}],
            "sys_attachment": [],
            "sys_audit": [],
        },
    }
    before_sha = digest(DOMAIN_TAG, before_state)
    audit = {
        "audit_id": "audit_0001",
        "table": "incident",
        "record_id": "inc_payroll_vpn",
        "field_changes": {
            "assignment_group": {"before": "Help Desk", "after": "Network Operations"},
            "priority": {"before": "4", "after": "2"},
            "cmdb_ci": {"before": "", "after": "ci_vpn_gateway_01"},
        },
    }
    after_state = {
        **base_meta,
        "generation": 1,
        "tables": {
            "cmdb_ci": [{"sys_id": "ci_vpn_gateway_01", "name": "vpn-gateway-01"}],
            "incident": [{"sys_id": "inc_payroll_vpn", "number": "INC0010001", "short_description": "Payroll users cannot reach VPN", "assignment_group": "Network Operations", "priority": "2", "state": "New", "cmdb_ci": "ci_vpn_gateway_01", "work_notes": ["Payroll cutover impact confirmed; starting VPN gateway health check."]}],
            "sys_attachment": [{"sys_id": "att_0001", "table": "incident", "record_id": "inc_payroll_vpn", "file_name": "vpn-diagnostic.txt", "content_sha256": "a" * 64}],
            "sys_audit": [audit],
        },
    }
    after_sha = digest(DOMAIN_TAG, after_state)
    event_body = {
        "schema": "flywheel.enterprise-environment-action-event/v1",
        "environment_id": ENVIRONMENT_ID,
        "run_id": "envrun_toy",
        "instance_id": "envinst_toy_a",
        "seq": 1,
        "request_id": "req_toy_0001",
        "surface": "agent_api",
        "actor": {"role": "agent_itil", "token_ref": "agent-token-digest:" + "b" * 64},
        "request": {"method": "PATCH", "path_template": "/api/now/table/incident/{sys_id}", "path_params": {"sys_id": "inc_payroll_vpn"}, "query_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "body_sha256": "c" * 64},
        "authorization": {"allowed": True, "reason": "ok"},
        "mutation": {"applied": True, "table": "incident", "record_id": "inc_payroll_vpn", "field_changes": audit["field_changes"]},
        "response": {"status": 200, "body_sha256": "e" * 64},
        "state": {"before_domain_state_sha256": before_sha, "after_domain_state_sha256": after_sha},
        "redaction": {"request_body_stored": False, "secret_values_present": False},
    }
    event_sha = digest(EVENT_TAG, event_body)
    action_log = {"schema": "flywheel.enterprise-environment-action-log/v1", "environment_id": ENVIRONMENT_ID, "run_id": "envrun_toy", "instance_id": "envinst_toy_a", "events": [{"event_sha256": event_sha, "event": event_body}]}
    action_log_sha = digest(LOG_TAG, action_log)
    snapshot = {"schema": "flywheel.enterprise-environment-state-snapshot/v1", "environment_id": ENVIRONMENT_ID, "run_id": "envrun_toy", "instance_id": "envinst_toy_a", "snapshot_kind": "after", "generation": 1, "descriptor_sha256": desc, "seed_sha256": seed, "domain_state_sha256": after_sha, "action_log_sha256": action_log_sha, "event_count": 1, "table_counts": {"cmdb_ci": 1, "incident": 1, "sys_attachment": 1, "sys_audit": 1}}
    snapshot_sha = digest(SNAPSHOT_TAG, snapshot)
    return {
        "domain_before_sha256": before_sha,
        "domain_after_sha256": after_sha,
        "action_event_sha256": event_sha,
        "action_log_sha256": action_log_sha,
        "snapshot_sha256": snapshot_sha,
        "preimages": {"domain_before": preimage(DOMAIN_TAG, before_state), "domain_after": preimage(DOMAIN_TAG, after_state), "action_event": preimage(EVENT_TAG, event_body), "action_log": preimage(LOG_TAG, action_log), "snapshot": preimage(SNAPSHOT_TAG, snapshot)},
    }
