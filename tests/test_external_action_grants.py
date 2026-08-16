from types import MappingProxyType
import json

import pytest

from harness.gateway_operation import (
    GatewayOperationError,
    canonicalize_operation,
)
from harness.gateway_grant_route import (
    authorize_gateway_operation, gateway_grant_post)
from harness.gateway_actions import dispatch_builtin
from harness.gateway_provider_adapter import resolve_credentials
from harness.journey_store import JourneyStore, MutationCommand


@pytest.mark.parametrize(("action", "operation", "scopes"), [
    ("chat.complete", {"model": "local", "messages": [
        {"role": "user", "content": "hello"}], "stream": True,
        "data_refs": [], "credential_refs": []},
     ("network",)),
    ("agent.run", {"goal": "inspect", "endpoint": "local", "max_steps": 2,
                   "allow_write": True, "allow_exec": False, "stream": True,
                   "data_refs": [], "credential_refs": []},
     ("write", "network")),
    ("workflow.run", {"workflow": "research-brief", "goal": "inspect",
                      "endpoint": "local", "allow_write": False,
                      "allow_exec": True, "data_refs": [],
                      "credential_refs": []}, ("exec", "network")),
    ("marketplace.install", {"name": "filesystem", "data_refs": [],
                              "credential_refs": []}, ("write", "plugin")),
])
def test_server_derives_ordered_scopes_from_exact_operation(
        action, operation, scopes):
    snapshot = canonicalize_operation(action, operation)
    assert snapshot.scopes == scopes
    assert snapshot.tool == action
    assert isinstance(snapshot.operation, MappingProxyType)


def test_nested_operation_is_immutable_after_admission():
    arguments = {"items": [{"value": "before"}]}
    snapshot = canonicalize_operation("plugin.call", {
        "name": "custom", "tool": "run", "arguments": arguments,
        "data_refs": [],
        "credential_refs": ["cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]})
    arguments["items"][0]["value"] = "after"
    assert snapshot.arguments_sha256 == canonicalize_operation(
        "plugin.call", {"name": "custom", "tool": "run",
                        "arguments": {"items": [{"value": "before"}]},
                        "data_refs": [],
                        "credential_refs": [
                            "cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]},
    ).arguments_sha256
    assert snapshot.scopes == ("write", "exec", "network", "plugin", "secrets")


@pytest.mark.parametrize("operation", [
    {"name": "x", "command": ["TOKEN=value"], "detail": "safe",
     "data_refs": [], "credential_refs": []},
    {"name": "x", "command": ["tool", "--api-key", "value"],
     "detail": "safe", "data_refs": [], "credential_refs": []},
    {"name": "x", "command": ["https://user:pass@example.invalid"],
     "detail": "safe", "data_refs": [], "credential_refs": []},
])
def test_inline_credentials_are_rejected_in_favor_of_handles(operation):
    with pytest.raises(GatewayOperationError) as failure:
        canonicalize_operation("plugin.register", operation)
    assert failure.value.code == "INVALID_REQUEST"


def test_unknown_fields_null_optionals_and_bad_handle_fail_closed():
    base = {"name": "x", "tool": "run", "arguments": {},
            "data_refs": [], "credential_refs": []}
    for changed in ({**base, "extra": 1}, {**base, "tool": None},
                    {**base, "credential_refs": ["raw-secret"]}):
        with pytest.raises(GatewayOperationError):
            canonicalize_operation("plugin.call", changed)


@pytest.mark.parametrize("action,operation", [
    ("plugin.register", {"name": "x", "command": ["tool", "--header",
      "Authorization: Bearer synthetic-marker-123456"], "detail": "safe",
      "data_refs": [], "credential_refs": []}),
    ("plugin.call", {"name": "x", "tool": "run", "arguments": {
      "headers": ["Authorization: Basic synthetic-marker-123456"]},
      "data_refs": [], "credential_refs": []}),
    ("plugin.call", {"name": "x", "tool": "run", "arguments": {
      "url": "https://example.invalid/#access_token=synthetic-marker-123456"},
      "data_refs": [], "credential_refs": []}),
])
def test_nested_header_and_fragment_credentials_are_refused(action, operation):
    with pytest.raises(GatewayOperationError) as failure:
        canonicalize_operation(action, operation)
    assert failure.value.code == "INVALID_REQUEST"
    assert "synthetic-marker" not in str(failure.value)


def _approved_plugin(root, monkeypatch):
    from harness import plugins
    owner, journey = "owner_" + "a" * 32, "jrn_" + "a" * 32
    now = "2026-08-15T12:00:00Z"
    monkeypatch.setenv("FLYWHEEL_HOME", str(root))
    assert plugins.register_mcp("mutable", ["safe-mcp"], requires=[])[
        "registered"] == "mutable"
    head = JourneyStore(root).create(MutationCommand(
        owner, journey, None, "create-1", "intake",
        {"legacy_label": None, "goal": "bind plan", "intake": {},
         "occurred_at": now})).event_head_sha256
    operation = {"name": "mutable", "tool": "run", "arguments": {},
                 "data_refs": [], "credential_refs": []}
    prepare = {"schema": "flywheel.gateway-operation/v1",
               "journey_ref": journey, "expected_event_head": head,
               "client_request_id": "request-1", "operation": operation}
    proposal, _ = gateway_grant_post(
        "/api/gateway-grants/prepare/plugin.call", json.dumps(prepare).encode(),
        owner_ref=owner, state_root=root, clock=lambda: now)
    approval, _ = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=owner, state_root=root, clock=lambda: now)
    final = {key: value for key, value in prepare.items() if key != "operation"}
    final.update(operation); final["grant_ref"] = approval["grant_ref"]
    return owner, now, final


def test_plugin_plan_change_rejects_without_burning_grant(tmp_path, monkeypatch):
    from harness import plugins
    owner, now, final = _approved_plugin(tmp_path, monkeypatch)
    registry = json.loads((tmp_path / "plugins.json").read_text())
    registry["mcp"][0]["command"] = ["different-mcp"]
    (tmp_path / "plugins.json").write_text(json.dumps(registry))
    with pytest.raises(GatewayOperationError) as failure:
        authorize_gateway_operation(
            "plugin.call", json.dumps(final).encode(), owner_ref=owner,
            state_root=tmp_path, clock=lambda: now)
    assert failure.value.code == "PERMISSION_DENIED"
    registry["mcp"][0]["command"] = ["safe-mcp"]
    (tmp_path / "plugins.json").write_text(json.dumps(registry))
    assert authorize_gateway_operation(
        "plugin.call", json.dumps(final).encode(), owner_ref=owner,
        state_root=tmp_path, clock=lambda: now).grant_ref == final["grant_ref"]


def test_authorized_plugin_dispatch_uses_frozen_launch(tmp_path, monkeypatch):
    owner, now, final = _approved_plugin(tmp_path, monkeypatch)
    authorized = authorize_gateway_operation(
        "plugin.call", json.dumps(final).encode(), owner_ref=owner,
        state_root=tmp_path, clock=lambda: now)
    registry = json.loads((tmp_path / "plugins.json").read_text())
    registry["mcp"][0]["command"] = ["latest-mcp"]
    (tmp_path / "plugins.json").write_text(json.dumps(registry))
    launches = []

    class Client:
        def __init__(self, command, **_kwargs): launches.append(command)
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def call_text(self, _tool, _arguments): return "ok"

    monkeypatch.setattr("harness.mcp_client.MCPClient", Client)
    result, status = dispatch_builtin(resolve_credentials(authorized, tmp_path))
    assert status == 200 and result["result"] == "ok"
    assert tuple(launches[0].argv) == ("safe-mcp",)
