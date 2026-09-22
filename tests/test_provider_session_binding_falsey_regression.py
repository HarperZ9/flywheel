from __future__ import annotations

from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_route import route_gateway_operation
from harness.gateway_operations import GatewayOperations

from provider_session_fixtures import (
    OWNER,
    JOURNEY,
    NOW,
    create_journey,
    dispatch,
    operation_result,
    provider_factory,
    service_with_journey,
    turn_raw,
)
from test_codex_provider_session import Events, Server, adapter_for, operation, request
from test_provider_session_operation_bindings import CountingAdapter
from test_provider_session_route_registry import (
    RouteRegistry,
    _authorized_raw,
    _factory,
    _grant_request,
    _operation,
    _prepare_and_approve,
)


def _prepare(tmp_path, head, registry, operation_value, *, request_id):
    return gateway_grant_post(
        "/api/gateway-grants/prepare/provider.session.turn",
        _grant_request(head, operation_value, request_id=request_id),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
        provider_session_registry=registry)


def _refresh_binding_fields(registry, head, operation_value):
    binding = registry.binding_snapshot(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        operation=operation_value)
    operation_value["config_digest"] = binding["config_digest"]
    operation_value["capability_digest"] = binding["capability_digest"]
    operation_value["provider_binding_ref"] = binding["provider_binding_ref"]
    registry.calls.clear()


def test_grant_prepare_rejects_empty_required_binding_values(tmp_path):
    for field in ("workspace_ref", "config_digest", "provider_binding_ref"):
        root = tmp_path / field
        root.mkdir()
        head = create_journey(root)
        registry = RouteRegistry()
        operation_value = _operation(registry, head)
        operation_value[field] = ""
        if field == "workspace_ref":
            _refresh_binding_fields(registry, head, operation_value)

        response, status = _prepare(
            root, head, registry, operation_value,
            request_id=f"prepare-empty-{field}")

        assert status != 200
        assert response["error"]["code"] in {
            "INVALID_REQUEST", "AGENT_BINDING_DRIFT"}


def test_grant_prepare_rejects_provider_binding_ref_mismatch(tmp_path):
    head = create_journey(tmp_path)
    registry = RouteRegistry()
    operation_value = _operation(registry, head)
    operation_value["provider_binding_ref"] = "psb_" + "b" * 32

    response, status = _prepare(
        tmp_path, head, registry, operation_value,
        request_id="prepare-binding-ref-mismatch")

    assert status != 200
    assert response["error"]["code"] == "AGENT_BINDING_DRIFT"


def test_dispatch_rejects_empty_required_binding_values_before_adapter(tmp_path):
    for field in ("workspace_ref", "config_digest"):
        root = tmp_path / field
        root.mkdir()
        service, head = service_with_journey(root)
        adapter = CountingAdapter()

        response = dispatch(
            service,
            turn_raw(head, request_id=f"dispatch-empty-{field}", **{field: ""}),
            provider_factory(adapters={"codex": adapter}))

        assert adapter.turn_calls == 0
        if response.status == 200:
            result = operation_result(service)
            assert result["reason"] == "AGENT_BINDING_DRIFT"
        else:
            assert response.body["error"]["code"] in {
                "INVALID_REQUEST", "AGENT_BINDING_DRIFT"}


def test_dispatch_rejects_empty_provider_binding_ref_before_adapter(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = CountingAdapter()

    response = dispatch(
        service, turn_raw(head, provider_binding_ref=""),
        provider_factory(adapters={"codex": adapter}))

    assert response.status == 422
    assert response.body["error"]["code"] == "INVALID_REQUEST"
    assert adapter.turn_calls == 0


def test_grant_backed_dispatch_rejects_provider_binding_ref_mismatch(tmp_path):
    head = create_journey(tmp_path)
    registry = RouteRegistry()
    operation_value = _operation(registry, head)
    grant_ref = _prepare_and_approve(
        tmp_path, registry, head, operation_value,
        request_id="dispatch-binding-ref-mismatch")
    service = GatewayOperations(tmp_path, clock=lambda: NOW, lock_timeout_s=0.5)
    tampered = {**operation_value, "provider_binding_ref": "psb_" + "b" * 32}

    response = route_gateway_operation(
        "POST", "/api/provider-sessions/turn", owner_ref=OWNER,
        service=service, process_factory=_factory(registry),
        raw=_authorized_raw(
            head, tampered, grant_ref,
            request_id="dispatch-binding-ref-mismatch"),
        content_type="application/json")

    assert response.status != 200
    assert response.body["error"]["code"] in {
        "AGENT_BINDING_DRIFT", "IDEMPOTENCY_MISMATCH", "PERMISSION_DENIED"}
    assert registry.adapter.calls == 0


def test_codex_adapter_rejects_empty_binding_value_before_native_request():
    for field in ("workspace_ref", "config_digest"):
        server = Server()

        outcome = adapter_for(server).start_turn(
            request(operation(**{field: ""})), emit=Events(),
            request_approval=lambda _: None, cancelled=lambda: False)

        assert outcome.state == "failed"
        assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
        assert server.outgoing.lines.empty()
