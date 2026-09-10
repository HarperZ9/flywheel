"""Relay-specific checks for the frozen gateway smoke."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


def _request_json(request_fn: Callable, base: str, path: str, token: str | None,
                  *, body: dict | None = None,
                  secret_values: tuple[str, ...] = ()) -> tuple[int, dict]:
    status, text = request_fn(
        base, path, token, body=body, secret_values=secret_values)
    try:
        return status, json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("RELAY_JSON_RESPONSE") from exc


def relay_status_smoke(base: str, token: str, home: Path, owner_ref: str,
                       secret_values: tuple[str, ...], request_fn: Callable,
                       require: Callable[[bool, str], None]) -> dict:
    from harness.bundled_lane_expectations import expected_bundled_lane
    from harness.journey_store import JourneyStore, MutationCommand

    expected = expected_bundled_lane("relay")
    status, roster = _request_json(
        request_fn, base, "/api/lanes", token, secret_values=secret_values)
    require(status == 200, "RELAY_ROSTER_HTTP")
    lanes = roster.get("lanes", [])
    relay = next((row for row in lanes if row.get("name") == "relay"), None)
    require(isinstance(relay, dict), "RELAY_ROSTER_MISSING")
    runtime = relay.get("resolved_runtime", {})
    require(runtime.get("selected_runtime") == "bundled",
            "RELAY_BUNDLED_RUNTIME")
    require(runtime.get("capability", {}).get("probed") is False,
            "RELAY_ROSTER_PROBED")
    launch = runtime.get("launch", {})
    require(launch.get("inherit_env") is False, "RELAY_ENV_INHERITANCE")
    require(launch.get("hide_window") is True, "RELAY_WINDOW_HIDDEN")
    require(launch.get("allowed_tools") == ["relay.status"],
            "RELAY_ALLOWED_TOOLS")
    component = runtime.get("bundled_component", {})
    require(component.get("descriptor_sha256") == expected["descriptor_sha256"],
            "RELAY_DESCRIPTOR_DIGEST")
    require(component.get("source_manifest_sha256")
            == expected["source_manifest_sha256"], "RELAY_SOURCE_DIGEST")
    require(component.get("source_commit") == expected["source_commit"],
            "RELAY_SOURCE_COMMIT")

    state = home / "state"
    journey_ref = "jrn_" + "9" * 32
    event_head = JourneyStore(state).create(MutationCommand(
        owner_ref, journey_ref, None, "frozen-relay-status-create", "intake",
        {"legacy_label": None, "goal": "read bundled Relay status",
         "intake": {}, "occurred_at": "2026-09-10T12:00:00Z"})).event_head_sha256
    operation = {"name": "relay", "tool": "relay.status", "args": {},
                 "governance_tier": "T2", "timeout": 10,
                 "data_refs": [], "credential_refs": []}
    request = {
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": journey_ref,
        "expected_event_head": event_head,
        "client_request_id": "frozen-relay-status",
        "operation": operation,
    }
    status, proposal = _request_json(
        request_fn, base, "/api/gateway-grants/prepare/lane.call", token,
        body=request, secret_values=secret_values)
    require(status == 200, "RELAY_GRANT_PREPARE")
    status, approval = _request_json(
        request_fn, base, "/api/gateway-grants/approve-once", token,
        body={"proposal_ref": proposal.get("proposal_ref")},
        secret_values=secret_values)
    require(status == 200, "RELAY_GRANT_APPROVE")
    status, relay_status = _request_json(
        request_fn, base, "/api/lane/relay/relay.status?frozen=1", token,
        body={
            "schema": request["schema"],
            "journey_ref": journey_ref,
            "expected_event_head": event_head,
            "client_request_id": request["client_request_id"],
            "grant_ref": approval.get("grant_ref"),
            **operation,
        },
        secret_values=secret_values)
    require(status == 200, "RELAY_STATUS_HTTP")
    require(relay_status.get("ok") is True, "RELAY_STATUS_NOT_OK")
    require(relay_status.get("server") == "relay", "RELAY_STATUS_SERVER")
    require(relay_status.get("version") == expected["version"],
            "RELAY_STATUS_VERSION")
    suffix_request = {**request, "client_request_id": "frozen-relay-status-suffix"}
    status, proposal = _request_json(
        request_fn, base, "/api/gateway-grants/prepare/lane.call", token,
        body=suffix_request, secret_values=secret_values)
    require(status == 200, "RELAY_SUFFIX_GRANT_PREPARE")
    status, approval = _request_json(
        request_fn, base, "/api/gateway-grants/approve-once", token,
        body={"proposal_ref": proposal.get("proposal_ref")},
        secret_values=secret_values)
    require(status == 200, "RELAY_SUFFIX_GRANT_APPROVE")
    suffix_body = {
        "schema": suffix_request["schema"],
        "journey_ref": journey_ref,
        "expected_event_head": event_head,
        "client_request_id": suffix_request["client_request_id"],
        "grant_ref": approval.get("grant_ref"),
        **operation,
    }
    status, suffix = _request_json(
        request_fn, base, "/api/lane/relay/relay.status/extra", token,
        body=suffix_body, secret_values=secret_values)
    require(status == 400 and suffix.get("code") == "GATEWAY_ROUTE_MALFORMED",
            "RELAY_SUFFIX_ROUTE_ADMITTED")
    status, suffix_retry = _request_json(
        request_fn, base, "/api/lane/relay/relay.status", token,
        body=suffix_body, secret_values=secret_values)
    require(status == 403 and suffix_retry.get("error", {}).get("code")
            == "APPROVAL_EXPIRED", "RELAY_SUFFIX_GRANT_NOT_CONSUMED")
    status, refused = _request_json(
        request_fn, base, "/api/relay/start", token,
        body={"goal": "blocked packaged Relay launch", "allow_exec": True},
        secret_values=secret_values)
    require(status == 403 and refused.get("code") == "CAPABILITY_NOT_ADMITTED",
            "RELAY_START_ADMITTED")
    return {
        "selected_runtime": runtime.get("selected_runtime"),
        "descriptor_sha256": component.get("descriptor_sha256"),
        "source_manifest_sha256": component.get("source_manifest_sha256"),
        "source_commit": component.get("source_commit"),
        "allowed_tools": launch.get("allowed_tools"),
        "status_server": relay_status.get("server"),
        "status_version": relay_status.get("version"),
        "suffix_status": suffix.get("code"),
        "suffix_retry_status": suffix_retry.get("error", {}).get("code"),
        "direct_start_status": status,
    }
