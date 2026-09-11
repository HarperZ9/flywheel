"""Synthetic approved model/root/budget drift controls."""
from dataclasses import replace
import pytest

from harness.gateway_operation import canonicalize_operation, GatewayOperationError, thaw_operation
from harness.plan_run_snapshot import thaw_json


def operation(**changes):
    return canonicalize_operation("agent.run", dict(goal="fixture", endpoint="ollama",
        max_steps=2, allow_write=False, allow_exec=False, stream=True,
        data_refs=[], credential_refs=[], **changes))


def test_old_operation_does_not_acquire_new_default_keys():
    assert not {"model", "max_tokens", "timeout_s"} & set(operation().operation)


@pytest.mark.parametrize("field,value", [("model", "x --bad"), ("model", ""),
    ("model", "x" * 161), ("max_tokens", True), ("max_tokens", 0),
    ("max_tokens", 32769), ("timeout_s", False), ("timeout_s", 1801)])
def test_strict_optional_binding_fields(field, value):
    with pytest.raises(GatewayOperationError): operation(**{field: value})


def test_explicit_and_default_selection_freeze_and_registry_drift_changes_digest(tmp_path, monkeypatch):
    from harness.gateway_agent_binding import freeze_agent_binding
    from harness.providers import REGISTRY
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOTS", raising=False)
    explicit = freeze_agent_binding(operation(model="fixture/model:tag"), tmp_path)
    frozen = thaw_json(explicit)
    assert frozen["model"]["model_id"] == "fixture/model:tag"
    assert frozen["model"]["selection"] == "explicit"
    assert frozen["workspace"]["root"] == str(tmp_path.resolve())
    assert frozen["budget"] == dict(max_steps=2, max_tokens=1024, timeout_s=300)
    original = freeze_agent_binding(operation(), tmp_path)
    monkeypatch.setitem(REGISTRY, "ollama", replace(REGISTRY["ollama"], default_model="changed"))
    assert freeze_agent_binding(operation(), tmp_path).sha256 != original.sha256
    assert thaw_json(explicit) == frozen


def test_policy_and_root_identity_are_frozen_and_child_does_not_reload_env(tmp_path, monkeypatch):
    from harness.gateway_agent_binding import freeze_agent_binding, validate_agent_binding
    from harness.gateway_agent_workspace import pinned_workspace
    allowed = tmp_path / "allowed"; allowed.mkdir()
    other = tmp_path / "other"; other.mkdir()
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOTS", str(allowed))
    op = operation(root=str(allowed))
    frozen = thaw_json(freeze_agent_binding(op, tmp_path))
    with pytest.raises(GatewayOperationError):
        freeze_agent_binding(operation(root=str(other)), tmp_path)
    monkeypatch.setenv("FLYWHEEL_WORKSPACE_ROOTS", str(other))
    validate_agent_binding(frozen, op)
    with pinned_workspace(frozen["workspace"]) as root:
        assert root == allowed
    old = tmp_path / "old"; allowed.rename(old); allowed.mkdir()
    with pytest.raises(GatewayOperationError):
        with pinned_workspace(frozen["workspace"]): pass


def test_changed_model_root_or_budget_cannot_use_frozen_binding(tmp_path, monkeypatch):
    from harness.gateway_agent_binding import freeze_agent_binding, validate_agent_binding
    monkeypatch.delenv("FLYWHEEL_WORKSPACE_ROOTS", raising=False)
    op = operation(model="fixture")
    binding = thaw_json(freeze_agent_binding(op, tmp_path))
    for changed in (operation(model="different"), operation(model="fixture", max_tokens=32),
                    operation(model="fixture", root=str(tmp_path))):
        with pytest.raises(GatewayOperationError): validate_agent_binding(binding, changed)


@pytest.mark.parametrize("endpoint", ["serve", "local", "claude-cli", "codex-cli", "opencode"])
def test_routes_without_bound_model_adapter_are_explicitly_unsupported(tmp_path, endpoint):
    from harness.gateway_agent_binding import freeze_agent_binding
    data = thaw_operation(operation().operation); data["endpoint"] = endpoint
    with pytest.raises(GatewayOperationError, match="AGENT_ENDPOINT_UNSUPPORTED"):
        freeze_agent_binding(canonicalize_operation("agent.run", data), tmp_path)
