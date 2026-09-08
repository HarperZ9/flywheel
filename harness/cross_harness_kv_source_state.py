"""State reconstruction and release-approval KV source branches."""
from __future__ import annotations

from typing import Any

from harness.cross_harness_oracle_support import _Malformed
from harness.cross_harness_kv_source_common import _answered, _field, _fields, _latest, _lowest, _records_with_type, _row_by_id


def _kv_msr_001(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _row_by_id(records)
    asset = _fields(rows, "asset-catalog:omega-742")
    case_id = _field(asset, "case_id")
    events = [
        row
        for row in _records_with_type(records, "event")
        if row["fields"].get("case_id") == case_id
    ]
    current = _latest([row for row in events if "superseded_by" not in row["fields"]], "sequence")
    state = _field(current["fields"], "state")
    exception = next(
        (
            row
            for row in _records_with_type(records, "exception")
            if row["fields"].get("case_id") == case_id
            and row["fields"].get("when_state") == state
        ),
        None,
    )
    if exception is None:
        raise _Malformed("fixture_required_record_missing")
    return _answered(
        task_id,
        {
            "case_id": case_id,
            "owner": _field(asset, "owner"),
            "component": _field(asset, "component"),
            "current_state": state,
            "latest_sequence": _field(current["fields"], "sequence"),
            "required_action": _field(exception["fields"], "required_action"),
            "due_date": _field(exception["fields"], "due_date"),
        },
        ["asset-catalog:omega-742", str(current["record_id"]), str(exception["record_id"])],
    )


def _kv_msr_002(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _row_by_id(records)
    shipment = _fields(rows, "shipment:bravo-6")
    shipment_id = _field(shipment, "shipment_id")
    approved_routes = [
        row
        for row in _records_with_type(records, "route_update")
        if row["fields"].get("shipment_id") == shipment_id
        and row["fields"].get("status") == "APPROVED"
    ]
    route_row = _latest(approved_routes, "revision")
    approved_caps = [
        row
        for row in _records_with_type(records, "capacity_override")
        if row["fields"].get("shipment_id") == shipment_id
        and row["fields"].get("status") == "APPROVED"
    ]
    cap_row = _lowest(approved_caps, "max_crates")
    cancellations = [
        row
        for row in _records_with_type(records, "cancellation")
        if row["fields"].get("shipment_id") == shipment_id
        and row["fields"].get("status") == "APPROVED"
    ]
    cancellation = cancellations[0] if cancellations else None
    if cancellation is None:
        raise _Malformed("fixture_required_record_missing")
    accepted = min(_field(shipment, "base_crates"), _field(cap_row["fields"], "max_crates"))
    accepted -= _field(cancellation["fields"], "cancelled_crates")
    return _answered(
        task_id,
        {
            "shipment_id": shipment_id,
            "route": _field(route_row["fields"], "route"),
            "accepted_crates": accepted,
            "temperature_mode": _field(shipment, "temperature_mode"),
            "release_gate": _field(cancellation["fields"], "release_gate"),
        },
        [
            "shipment:bravo-6",
            str(route_row["record_id"]),
            str(cap_row["record_id"]),
            str(cancellation["record_id"]),
        ],
    )


def _kv_rap_001(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    approved = [
        row
        for row in _records_with_type(records, "policy_revision")
        if row["fields"].get("policy_id") == "ctx-window"
        and row["fields"].get("status") == "APPROVED"
    ]
    active = _latest(approved, "revision")["fields"]
    return _answered(
        task_id,
        {
            "policy_id": _field(active, "policy_id"),
            "active_revision": _field(active, "revision"),
            "context_tokens": _field(active, "context_tokens"),
            "max_output_tokens": _field(active, "max_output_tokens"),
            "cache_reuse_between_arms": _field(active, "cache_reuse_between_arms"),
            "reason": "latest_approved_revision",
        },
        [
            "policy:ctx-window:rev12",
            "policy:ctx-window:rev14",
            "override:unsigned-river",
            "approver-registry:ctx-window",
        ],
    )


def _kv_rap_002(task_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _row_by_id(records)
    source = _fields(rows, "source:serving:43640b2")
    heavy_state = _field(_fields(rows, "ci:heavy-source:pending"), "heavy_source_tests")
    approval = _fields(rows, "approval:default-change:absent")
    approved = _field(approval, "default_change_approved")
    blockers: list[str] = []
    if heavy_state != "passed":
        blockers.append("heavy_source_tests_pending")
    if approved is not True:
        blockers.append("no_default_change_approval")
    return _answered(
        task_id,
        {
            "candidate": _field(source, "candidate"),
            "source_state": _field(source, "source_state"),
            "allowed_use": "diagnostic_gate_only",
            "default_change_approved": approved,
            "blockers": blockers,
        },
        [
            "source:serving:43640b2",
            "review:serving:independent-pass",
            "ci:heavy-source:pending",
            "approval:default-change:absent",
        ],
    )


DERIVERS = {
    "kv-msr-001-incident-reconstruction": _kv_msr_001,
    "kv-msr-002-route-reconstruction": _kv_msr_002,
    "kv-rap-001-policy-precedence": _kv_rap_001,
    "kv-rap-002-release-approval": _kv_rap_002,
}
