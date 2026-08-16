import json

import pytest

from harness.gateway_envelope import parse_gateway_envelope
from harness.gateway_operation import (
    GatewayOperationError, canonicalize_operation, materialize_agent_attachment)
from harness.gateway_operations import GatewayOperations
from harness.gateway_operation_recovery import validate_operation_value
from harness.gateway_secret_boundary import validate_no_raw_secrets


HEAD = "a" * 64
JOURNEY = "jrn_" + "a" * 32
GRANT = "gnt_" + "a" * 32


def _raw(operation=None, **changes):
    body = {
        "schema": "flywheel.gateway-operation/v1", "journey_ref": JOURNEY,
        "expected_event_head": HEAD, "client_request_id": "request-1",
        "grant_ref": GRANT, "name": "gather", "data_refs": [],
        "credential_refs": [],
    }
    if operation is not None:
        body = {key: value for key, value in body.items() if key != "name"}
        body.update(operation)
    body.update(changes)
    return json.dumps(body, separators=(",", ":")).encode()


@pytest.mark.parametrize("field,value", [
    ("journey_ref", "../../escaped"), ("journey_ref", "%2e%2e/escaped"),
    ("journey_ref", "/absolute"), ("journey_ref", "C:\\outside"),
    ("journey_ref", "\\\\host\\share"), ("journey_ref", "."),
    ("expected_event_head", "not-a-head"), ("client_request_id", "../bad"),
    ("client_request_id", "bad\\request"), ("grant_ref", "not-a-grant"),
])
def test_complete_envelope_rejects_unsafe_selectors_before_io(field, value):
    with pytest.raises(GatewayOperationError) as failure:
        parse_gateway_envelope("plugin.probe", _raw(**{field: value}))
    assert failure.value.code == "INVALID_REQUEST"


def test_complete_envelope_is_closed_and_returns_canonical_operation():
    parsed = parse_gateway_envelope("plugin.probe", _raw())
    assert parsed.journey_ref == JOURNEY
    assert parsed.expected_event_head == HEAD
    assert parsed.client_request_id == "request-1"
    assert parsed.grant_ref == GRANT
    assert dict(parsed.operation.operation) == {
        "name": "gather", "data_refs": (), "credential_refs": (),
    }
    with pytest.raises(GatewayOperationError):
        parse_gateway_envelope("plugin.probe", _raw(extra="field"))


@pytest.mark.parametrize("value", [
    {"headers": ["Authorization: Bearer synthetic-marker-123456"]},
    {"headers": ["Cookie: session=synthetic-marker-123456"]},
    {"argv": ["tool", "--header", "Authorization: Basic c3ludGhldGlj"]},
    {"argv": ["tool", "--api-key", "synthetic-marker-123456"]},
    {"url": "https://user:pass@example.invalid/path"},
    {"url": "https://example.invalid/?api_key=synthetic-marker-123456"},
    {"url": "https://example.invalid/#token=synthetic-marker-123456"},
    {"url": "https://example.invalid/#token/rawvalue123456"},
    {"url": "https://example.invalid/#token:rawvalue123456"},
    {"headers": ["X-Api-Key: rawvalue123456"]},
    {"nested": [{"password": "synthetic-marker-123456"}]},
    {"headers": [["%41uthorization%3A%20Bearer%20synthetic-marker-123456"]]},
    {"argv": ["tool", "--token=synthetic-marker-123456"]},
    {"argv": ["tool", "--cookie", "synthetic-marker-123456"]},
    {"argv": ["tool", "--header", "X-Session: synthetic-marker-123456"]},
    {"credential_refs": ["synthetic-marker-123456"]},
    {"pass%77ord": "synthetic-marker-123456"},
])
def test_one_recursive_boundary_refuses_raw_credentials_without_echo(value):
    with pytest.raises(GatewayOperationError) as failure:
        validate_no_raw_secrets(value)
    assert failure.value.code == "INVALID_REQUEST"
    assert "synthetic-marker" not in str(failure.value)


def test_agent_attachment_is_closed_structured_relative_context():
    base = {"goal": "inspect", "endpoint": "local", "max_steps": 2,
            "allow_write": False, "allow_exec": False, "stream": True,
            "data_refs": [], "credential_refs": []}
    operation = canonicalize_operation("agent.run", {
        **base, "attachment": {
            "relative_path": "lib/main.dart", "selection": "selected"}})
    assert dict(operation.operation["attachment"]) == {
        "relative_path": "lib/main.dart", "selection": "selected"}
    for unsafe in (r"C:\private\main.dart", "C:/private/main.dart",
                   "/private/main.dart", "../main.dart", "%2e%2e/main.dart"):
        with pytest.raises(GatewayOperationError) as failure:
            canonicalize_operation("agent.run", {
                **base, "attachment": {
                    "relative_path": unsafe, "selection": "selected"}})
        assert failure.value.code == "INVALID_REQUEST"
        assert "private" not in str(failure.value)
    rendered = materialize_agent_attachment(dict(operation.operation))
    assert rendered["goal"] == (
        "Active source: lib/main.dart\nSelected text:\nselected\nRequest:\ninspect")
    assert "attachment" not in rendered


def test_cancel_envelope_has_exact_operation_destination_tool_and_scope():
    ref = "op_" + "b" * 32
    parsed = parse_gateway_envelope("operation.cancel", _raw(operation={
        "operation_ref": ref, "timeout_ms": 5_000,
        "data_refs": [], "credential_refs": [],
    }))

    assert dict(parsed.operation.operation) == {
        "operation_ref": ref, "timeout_ms": 5_000,
        "data_refs": (), "credential_refs": (),
    }
    assert parsed.operation.tool == "operation.cancel"
    assert dict(parsed.operation.destination) == {"kind": "operation", "ref": ref}
    assert parsed.operation.scopes == ("exec",)

    with pytest.raises(GatewayOperationError) as failure:
        parse_gateway_envelope("operation.cancel", _raw(operation={
            "operation_ref": ref, "timeout_ms": 5_000,
            "data_refs": ["data_public"], "credential_refs": [],
        }))
    assert failure.value.code == "INVALID_REQUEST"


def test_operation_result_uses_shared_signed64_integer_domain(tmp_path):
    service = GatewayOperations(tmp_path, clock=lambda: "2026-08-16T12:00:00Z")
    owner, operation = "owner_" + "a" * 32, "op_" + "a" * 32
    valid = {"minus53": -(1 << 53), "plus53": 1 << 53,
             "min64": -(1 << 63), "max64": (1 << 63) - 1}

    assert service._seal(owner, operation, "agent.run", "completed", valid) == (
        "ae2e1e88cc232bbe608404be0efb6ed20f43d72db9b018a1fd3d80cea64544a8")
    for overflow in (1 << 63, -(1 << 63) - 1):
        with pytest.raises(GatewayOperationError) as failure:
            service._seal(owner, operation, "agent.run", "completed",
                          {"nested": [overflow]})
        assert failure.value.code == "STORE_COMMIT_FAILED"


def test_exact_credential_guard_checks_decoded_values_not_schema_keys():
    validate_operation_value({"state": "completed"}, ("state",))
    with pytest.raises(ValueError):
        validate_operation_value({"state": "contains-state"}, ("state",))
