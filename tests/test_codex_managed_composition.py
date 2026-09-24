from __future__ import annotations

import hashlib
import json

import pytest

from harness.codex_managed_composition import (
    ManagedCodexCompositionError,
    build_managed_codex_components,
    managed_codex_server_config,
)
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_route import route_gateway_operation
from harness.gateway_operations import GatewayOperations
from provider_session_fixtures import NOW, create_journey


OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
HEAD = "b" * 64


def _repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    return root


def _config(tmp_path, *, model="gpt-5.6-sol"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    exe = tmp_path / "codex.exe"
    exe.write_bytes(b"synthetic codex executable")
    return managed_codex_server_config(
        executable=exe,
        executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
        model=model,
        codex_version="configured-test-version",
        policy_root=tmp_path / "policy",
    )


def _snapshot(registry, workspace_ref, *, model="gpt-5.6-sol", head=HEAD):
    return registry.binding_snapshot(
        owner_ref=OWNER,
        journey_ref=JOURNEY,
        expected_event_head=head,
        operation={
            "provider": "codex",
            "workspace_ref": workspace_ref,
            "model": model,
            "permission_scope": {"mode": "manual"},
        },
    )


def test_disabled_components_install_account_manager_without_ambient_codex(tmp_path, monkeypatch):
    repo = _repo(tmp_path)

    def forbidden_connect():
        raise AssertionError("ambient Codex connection was attempted")

    monkeypatch.setattr(
        "harness.codex_account_sessions.CodexAppServerClient.connect",
        forbidden_connect,
    )
    components = build_managed_codex_components(
        repo_root=repo,
        run_root=tmp_path / "run",
        state_root=tmp_path / "state",
        clock=lambda: "2026-09-16T12:00:00Z",
    )

    body, status = components.codex_account_manager.read_status(OWNER)

    assert status == 503
    assert body["state"] == "unavailable"
    assert body["reason"] == "AGENT_NATIVE_RUNTIME_DISABLED"
    assert components.operation_process_factory.provider_session_adapters == {}
    assert components.operation_process_factory.provider_session_registry is components.provider_session_registry
    assert components.provider_session_registry.adapter_for(authorized=None, operation_ref="op") is None


def test_config_validation_fails_closed_before_any_managed_process(tmp_path):
    exe = tmp_path / "codex.exe"
    exe.write_bytes(b"synthetic codex executable")

    with pytest.raises(ManagedCodexCompositionError) as partial:
        managed_codex_server_config(executable=exe)
    assert partial.value.code == "AGENT_NATIVE_CONFIG_INCOMPLETE"

    with pytest.raises(ManagedCodexCompositionError) as wrong_hash:
        managed_codex_server_config(
            executable=exe,
            executable_sha256="0" * 64,
            model="gpt-5.6-sol",
            codex_version="configured-test-version",
            policy_root=tmp_path / "policy",
        )
    assert wrong_hash.value.code == "AGENT_NATIVE_EXECUTABLE_MISMATCH"

    with pytest.raises(ManagedCodexCompositionError) as bad_model:
        managed_codex_server_config(
            executable=exe,
            executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
            model="bad\nmodel",
            codex_version="configured-test-version",
            policy_root=tmp_path / "policy",
        )
    assert bad_model.value.code == "MODEL_SELECTION_REQUIRED"


def test_managed_config_without_lifecycle_reports_baseline_pending(tmp_path, monkeypatch):
    repo = _repo(tmp_path)

    def forbidden_connect():
        raise AssertionError("ambient Codex connection was attempted")

    monkeypatch.setattr(
        "harness.codex_account_sessions.CodexAppServerClient.connect",
        forbidden_connect,
    )
    components = build_managed_codex_components(
        repo_root=repo,
        run_root=tmp_path / "run",
        state_root=tmp_path / "state",
        clock=lambda: "2026-09-16T12:00:00Z",
        config=_config(tmp_path),
    )

    body, status = components.codex_account_manager.read_status(OWNER)
    start, start_status = components.codex_account_manager.start_login(
        OWNER, "browser", visible_ui_action=True)

    assert status == 503
    assert body["state"] == "baseline_pending"
    assert start_status == 503
    assert start["state"] == "baseline_pending"


def test_codex_registry_is_deterministic_non_admitted_and_model_workspace_bound(tmp_path):
    repo = _repo(tmp_path)
    components = build_managed_codex_components(
        repo_root=repo,
        run_root=tmp_path / "run",
        state_root=tmp_path / "state",
        clock=lambda: "2026-09-16T12:00:00Z",
        config=_config(tmp_path, model="gpt-5.6-sol"),
    )
    workspace_ref = components.composition.workspace.workspace_ref

    first = _snapshot(components.provider_session_registry, workspace_ref)
    second = _snapshot(components.provider_session_registry, workspace_ref)
    wrong_workspace = _snapshot(components.provider_session_registry, "0" * 64)
    wrong_model = _snapshot(
        components.provider_session_registry, workspace_ref, model="gpt-5.6-terra")

    assert first["provider"] == "codex"
    assert first["admitted"] is False
    assert first["reason"] == "AGENT_NATIVE_BASELINE_PENDING"
    assert first["runtime_kind"] == "codex-managed-owned-held"
    assert first["config_digest"] == second["config_digest"]
    assert first["capability_digest"] == second["capability_digest"]
    assert first["provider_binding_ref"] == second["provider_binding_ref"]
    assert wrong_workspace["admitted"] is False
    assert wrong_workspace["reason"] == "AGENT_BINDING_DRIFT"
    assert wrong_model["admitted"] is False
    assert wrong_model["reason"] == "AGENT_BINDING_DRIFT"


def test_provider_turn_with_matching_codex_binding_remains_incomplete(tmp_path):
    repo = _repo(tmp_path)
    state_root = tmp_path / "state"
    components = build_managed_codex_components(
        repo_root=repo,
        run_root=tmp_path / "run",
        state_root=state_root,
        clock=lambda: NOW,
        config=_config(tmp_path),
    )
    head = create_journey(state_root)
    workspace_ref = components.composition.workspace.workspace_ref
    snapshot = _snapshot(components.provider_session_registry, workspace_ref, head=head)
    operation = {
        "provider": "codex",
        "workspace_ref": workspace_ref,
        "model": "gpt-5.6-sol",
        "config_digest": snapshot["config_digest"],
        "capability_digest": snapshot["capability_digest"],
        "provider_binding_ref": snapshot["provider_binding_ref"],
        "permission_scope": {"mode": "manual"},
        "input": [{"type": "input_text", "text": "hi"}],
        "stream": True,
        "resume_policy": "new_thread",
        "data_refs": [],
        "credential_refs": [],
        "timeout_s": 1,
    }
    prepared, status = gateway_grant_post(
        "/api/gateway-grants/prepare/provider.session.turn",
        _grant_request(head, operation, request_id="composition-turn"),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW,
        provider_session_registry=components.provider_session_registry)
    assert status == 200, prepared
    approved, approved_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state_root, clock=lambda: NOW)
    assert approved_status == 200

    service = GatewayOperations(state_root, clock=lambda: NOW)
    response = route_gateway_operation(
        "POST", "/api/provider-sessions/turn", owner_ref=OWNER,
        service=service,
        process_factory=components.operation_process_factory,
        raw=_authorized_raw(
            head, operation, approved["grant_ref"],
            request_id="composition-turn"),
        content_type="application/json")

    assert response.status == 200
    assert response.stream is not None
    b"".join(response.stream)
    result = service.result(OWNER, next(iter(service.operation_refs(OWNER))))["result"]
    assert result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert result["runtime_execution_disabled"] is True


def test_replacement_cleanup_failure_installs_disabled_components_and_retains_custody(tmp_path):
    repo = _repo(tmp_path)

    class HeldLifecycle:
        def __init__(self):
            self.shutdown_calls = 0

        def account_client_for_owner(self, *, owner_ref):
            raise AssertionError("no client should be requested")

        def shutdown(self):
            self.shutdown_calls += 1
            return False

    lifecycle = HeldLifecycle()
    current = build_managed_codex_components(
        repo_root=repo,
        run_root=tmp_path / "run",
        state_root=tmp_path / "state-a",
        clock=lambda: "2026-09-16T12:00:00Z",
        config=_config(tmp_path / "a"),
        lifecycle=lifecycle,
    )

    replacement = build_managed_codex_components(
        repo_root=repo,
        run_root=tmp_path / "run",
        state_root=tmp_path / "state-b",
        clock=lambda: "2026-09-16T12:00:00Z",
        config=_config(tmp_path / "b"),
        current=current,
    )
    body, status = replacement.codex_account_manager.read_status(OWNER)

    assert lifecycle.shutdown_calls == 1
    assert replacement.composition.held_composition is current.composition
    assert status == 503
    assert body["state"] == "unavailable"
    assert body["reason"] == "AGENT_NATIVE_CLEANUP_REQUIRED"
    assert replacement.operation_process_factory.provider_session_registry is replacement.provider_session_registry
    held = _snapshot(replacement.provider_session_registry,
                     replacement.composition.workspace.workspace_ref)
    assert held["admitted"] is False
    assert held["reason"] == "AGENT_NATIVE_CLEANUP_REQUIRED"


def _grant_request(head: str, operation: dict, *, request_id: str) -> bytes:
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": request_id,
        "operation": operation,
    }, separators=(",", ":")).encode()


def _authorized_raw(head: str, operation: dict, grant_ref: str, *,
                    request_id: str) -> bytes:
    return json.dumps({
        "schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": head,
        "client_request_id": request_id,
        "grant_ref": grant_ref,
        **operation,
    }, separators=(",", ":")).encode()
