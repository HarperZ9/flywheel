from harness.provider_session_contract import (
    ProviderOperationOutcome,
    ProviderRuntimeBinding,
)

from provider_session_fixtures import (
    OWNER,
    dispatch,
    operation_result,
    provider_factory,
    service_with_journey,
    turn_raw,
)


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class CountingAdapter:
    provider = "codex"

    def __init__(self, *, config_digest="cfg-a", outcome=None):
        self.binding = ProviderRuntimeBinding(
            provider="codex", workspace_ref="workspace-a",
            config_digest=config_digest, capability_digest="cap-a")
        self.outcome = outcome or ProviderOperationOutcome.completed({
            "provider_session": {
                "provider": "codex",
                "native_session_id": "session-1",
                "native_thread_id": "thread-1",
                "native_turn_id": "turn-1",
                "last_provider_event_id": "event-1",
                "config_digest": config_digest,
                "capability_digest": "cap-a",
            },
            "history_status": "complete",
            "side_effect_status": "input_sent",
        })
        self.turn_calls = 0

    def current_binding(self):
        return self.binding

    def start_turn(self, request, *, emit, request_approval, cancelled):
        self.turn_calls += 1
        emit.native("input_sent", native_thread_id="thread-1")
        return self.outcome

    def resume(self, request, *, emit):
        raise AssertionError("resume should not be called")

    def reconcile(self, request, *, emit):
        raise AssertionError("reconcile should not be called")


def test_unapproved_provider_turn_dispatches_zero_inputs(tmp_path):
    service, head = service_with_journey(tmp_path, authorize=False)
    adapter = CountingAdapter()

    response = dispatch(
        service, turn_raw(head), provider_factory(adapters={"codex": adapter}))

    assert response.status == 403
    assert response.body["error"]["code"] == "PERMISSION_REQUIRED"
    assert adapter.turn_calls == 0
    assert service.operation_refs(OWNER) == set()


def test_provider_turn_route_enters_gateway_operation_with_runtime_disabled(tmp_path):
    service, head = service_with_journey(tmp_path)

    response = dispatch(service, turn_raw(head), provider_factory())

    assert response.status == 200
    result = operation_result(service)
    assert result["reason"] == "AGENT_NATIVE_INCOMPLETE"
    assert result["runtime_execution_disabled"] is True
    assert result["side_effect_status"] == "none"


def test_provider_http_mount_delegates_to_operation_route(monkeypatch):
    import io
    from harness import gateway
    from harness.gateway_operation_route import RouteResponse
    captured = {}

    def route(method, path, **values):
        captured.update(method=method, path=path, **values)
        return RouteResponse(200, {"accepted": True})

    monkeypatch.setattr(
        "harness.gateway_operation_route.route_gateway_operation", route)
    raw = b'{"bounded":true}'
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/provider-sessions/turn"
    handler.owner_ref = OWNER
    handler.headers = _Headers({
        "Content-Length": str(len(raw)),
        "Content-Type": "application/json; charset=utf-8",
    })
    handler.rfile = io.BytesIO(raw)
    handler._operation_components = lambda: ("service", "factory")
    handler._operation_response = lambda response: captured.update(response=response)

    assert handler._route_operation("POST") is True
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/provider-sessions/turn"
    assert captured["raw"] == raw
    assert captured["owner_ref"] == OWNER
    assert captured["content_type"] == "application/json"
    assert captured["response"].body == {"accepted": True}


def test_stale_adapter_config_fails_before_provider_input(tmp_path):
    service, head = service_with_journey(tmp_path)
    adapter = CountingAdapter(config_digest="cfg-stale")

    response = dispatch(
        service, turn_raw(head), provider_factory(adapters={"codex": adapter}))

    assert response.status == 200
    result = operation_result(service)
    assert result["reason"] == "AGENT_BINDING_DRIFT"
    assert result["expected_config_digest"] == "cfg-a"
    assert result["actual_config_digest"] == "cfg-stale"
    assert adapter.turn_calls == 0
