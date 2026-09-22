from __future__ import annotations

from codex_managed_runtime_fixtures import (
    OWNER,
    Starter,
    accept_auth_inventory,
    components,
    lifecycle,
    operation,
    prepare_approve_and_dispatch,
    roots,
    snapshot,
)
from harness.codex_managed_composition import build_managed_codex_components
from provider_session_fixtures import create_journey


def test_baseline_inventory_without_auth_extension_is_not_admitted(tmp_path):
    values = roots(tmp_path)
    starter = Starter()
    managed_lifecycle = lifecycle(values, starter)
    managed_lifecycle.ensure_baseline_inventory(OWNER)
    comp = components(values, managed_lifecycle)
    head = create_journey(values["state"])

    binding = snapshot(
        comp.provider_session_registry,
        comp.composition.workspace.workspace_ref,
        head=head)

    assert binding["admitted"] is False
    assert binding["reason"] == "AGENT_NATIVE_AUTH_REQUIRED"
    assert binding["runtime_kind"] == "codex-managed-owned-held"
    assert len(starter.sessions) == 1


def test_auth_inventory_binding_uses_runtime_client_digest_and_installs_broker(tmp_path):
    values = roots(tmp_path)
    starter = Starter(config_digest="cfg-auth-runtime")
    managed_lifecycle = lifecycle(values, starter)
    accept_auth_inventory(values, managed_lifecycle)
    comp = components(values, managed_lifecycle)
    head = create_journey(values["state"])

    binding = snapshot(
        comp.provider_session_registry,
        comp.composition.workspace.workspace_ref,
        head=head)

    assert binding["admitted"] is True
    assert binding["reason"] == "admitted"
    assert binding["config_digest"] == "cfg-auth-runtime"
    assert binding["runtime_kind"] == "codex-managed-owned-authenticated"
    assert starter.sessions[-1].closed is True
    assert comp.operation_process_factory.provider_session_approval_resolver is None
    assert comp.operation_process_factory.provider_session_approval_broker is not None


def test_binding_snapshot_closes_runtime_session_when_binding_inspection_fails(tmp_path):
    values = roots(tmp_path)
    starter = Starter(config_digest="")
    managed_lifecycle = lifecycle(values, starter)
    accept_auth_inventory(values, managed_lifecycle)
    comp = components(values, managed_lifecycle)
    head = create_journey(values["state"])

    binding = snapshot(
        comp.provider_session_registry,
        comp.composition.workspace.workspace_ref,
        head=head)

    assert binding["admitted"] is False
    assert binding["reason"] == "AGENT_NATIVE_RUNTIME_DISABLED"
    assert starter.sessions[-1].closed is True
    assert managed_lifecycle.shutdown() is True


def test_binding_snapshot_cleanup_failure_after_inspection_error_holds_custody(tmp_path):
    values = roots(tmp_path)
    starter = Starter(close_results=[True, False], config_digest="")
    managed_lifecycle = lifecycle(values, starter)
    accept_auth_inventory(values, managed_lifecycle)
    comp = components(values, managed_lifecycle)
    head = create_journey(values["state"])

    binding = snapshot(
        comp.provider_session_registry,
        comp.composition.workspace.workspace_ref,
        head=head)

    assert binding["admitted"] is False
    assert binding["reason"] == "AGENT_NATIVE_CLEANUP_REQUIRED"
    assert starter.sessions[-1].closed is False
    assert managed_lifecycle.shutdown() is False


def test_disabled_runtime_without_model_returns_held_snapshot(tmp_path):
    values = roots(tmp_path)
    comp = build_managed_codex_components(
        repo_root=values["workspace"],
        run_root=values["run"],
        state_root=values["state"],
        clock=lambda: "2026-09-16T12:00:00Z",
    )

    binding = comp.provider_session_registry.binding_snapshot(
        owner_ref=OWNER,
        journey_ref="jrn_" + "a" * 32,
        expected_event_head="b" * 64,
        operation={
            "provider": "codex",
            "workspace_ref": comp.composition.workspace.workspace_ref,
            "permission_scope": {"mode": "manual"},
        },
    )

    assert binding["admitted"] is False
    assert binding["reason"] == "AGENT_NATIVE_RUNTIME_DISABLED"
    assert binding["model"] == ""


def test_grant_backed_turn_uses_lazy_managed_codex_adapter(tmp_path):
    values = roots(tmp_path)
    starter = Starter(config_digest="cfg-turn-runtime")
    managed_lifecycle = lifecycle(values, starter)
    accept_auth_inventory(values, managed_lifecycle)
    comp = components(values, managed_lifecycle)
    head = create_journey(values["state"])
    binding = snapshot(
        comp.provider_session_registry,
        comp.composition.workspace.workspace_ref,
        head=head)

    result = prepare_approve_and_dispatch(
        comp, values["state"], head, operation(binding),
        request_id="managed-codex-turn")

    assert result["state"] == "completed"
    provider_session = result["result"]["provider_session"]
    assert provider_session["provider"] == "codex"
    assert provider_session["native_session_id"] == "session-1"
    assert provider_session["native_thread_id"] == "thread-1"
    assert provider_session["native_turn_id"] == "turn-1"
    assert provider_session["config_digest"] == "cfg-turn-runtime"
    assert starter.sessions[-1].input_sent is True
    assert starter.sessions[-1].closed is True


def test_cleanup_failure_after_provider_input_prevents_clean_completion(tmp_path):
    values = roots(tmp_path)
    starter = Starter(
        close_results=[True, True, True, True, True, False],
        config_digest="cfg-cleanup-runtime")
    managed_lifecycle = lifecycle(values, starter)
    accept_auth_inventory(values, managed_lifecycle)
    comp = components(values, managed_lifecycle)
    head = create_journey(values["state"])
    binding = snapshot(
        comp.provider_session_registry,
        comp.composition.workspace.workspace_ref,
        head=head)

    result = prepare_approve_and_dispatch(
        comp, values["state"], head, operation(binding),
        request_id="managed-codex-cleanup")

    assert result["state"] == "failed"
    assert result["result"]["reason"] == "AGENT_NATIVE_CLEANUP_REQUIRED"
    assert result["result"]["history_status"] == "indeterminate"
    assert result["result"]["side_effect_status"] == "indeterminate"
    assert starter.sessions[-1].input_sent is True
    assert starter.sessions[-1].closed is False
    assert managed_lifecycle.shutdown() is False
