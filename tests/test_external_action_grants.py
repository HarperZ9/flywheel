from types import MappingProxyType

import pytest

from harness.gateway_operation import (
    GatewayOperationError,
    canonicalize_operation,
)


@pytest.mark.parametrize(("action", "operation", "scopes"), [
    ("chat.complete", {"model": "local", "messages": [
        {"role": "user", "content": "hello"}], "stream": True},
     ("network",)),
    ("agent.run", {"goal": "inspect", "endpoint": "local", "max_steps": 2,
                   "allow_write": True, "allow_exec": False, "stream": True},
     ("write", "network")),
    ("workflow.run", {"workflow": "research-brief", "goal": "inspect",
                      "endpoint": "local", "allow_write": False,
                      "allow_exec": True}, ("exec", "network")),
    ("marketplace.install", {"name": "filesystem"}, ("write", "plugin")),
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
        "credential_refs": ["cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]})
    arguments["items"][0]["value"] = "after"
    assert snapshot.arguments_sha256 == canonicalize_operation(
        "plugin.call", {"name": "custom", "tool": "run",
                        "arguments": {"items": [{"value": "before"}]},
                        "credential_refs": [
                            "cred_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]},
    ).arguments_sha256
    assert snapshot.scopes == ("write", "exec", "network", "plugin", "secrets")


@pytest.mark.parametrize("operation", [
    {"name": "x", "command": ["TOKEN=value"], "detail": "safe",
     "credential_refs": []},
    {"name": "x", "command": ["tool", "--api-key", "value"],
     "detail": "safe", "credential_refs": []},
    {"name": "x", "command": ["https://user:pass@example.invalid"],
     "detail": "safe", "credential_refs": []},
])
def test_inline_credentials_are_rejected_in_favor_of_handles(operation):
    with pytest.raises(GatewayOperationError) as failure:
        canonicalize_operation("plugin.register", operation)
    assert failure.value.code == "INVALID_REQUEST"


def test_unknown_fields_null_optionals_and_bad_handle_fail_closed():
    base = {"name": "x", "tool": "run", "arguments": {},
            "credential_refs": []}
    for changed in ({**base, "extra": 1}, {**base, "tool": None},
                    {**base, "credential_refs": ["raw-secret"]}):
        with pytest.raises(GatewayOperationError):
            canonicalize_operation("plugin.call", changed)
