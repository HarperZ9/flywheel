from harness import endpoints
from harness import gateway
from harness import gateway_openai_route as route


def _roster():
    return {"endpoints": [{"name": "codex-cli", "credential": "cli-auth"}],
            "usable_names": ["codex-cli"]}


def _codex_backend(monkeypatch):
    backend = endpoints.CliBackend(
        "codex-plan", ["codex", "exec", "--model", "{model}", "{prompt}"],
        "configured")
    monkeypatch.setattr(endpoints, "build_endpoints", lambda **_kwargs: [backend])
    return backend


def test_route_request_returns_typed_model_selection_required_without_provider_call(monkeypatch):
    _codex_backend(monkeypatch)
    calls = []

    def route_answer(*_args, **_kwargs):
        calls.append("provider")
        raise AssertionError("provider call should not start")

    body, status = route.route_request(
        "hello", "codex-cli", "",
        unified_roster=_roster,
        router_ledger=lambda: object(),
        route_answer=route_answer)

    assert status == 422
    assert body == {
        "schema": "flywheel.evidence-transport-error/v1",
        "error": {
            "code": "MODEL_SELECTION_REQUIRED",
            "message": "codex-cli requires an explicit model selection",
        },
    }
    assert calls == []


def test_openai_chat_returns_typed_model_selection_required_for_codex_cli(monkeypatch):
    _codex_backend(monkeypatch)
    def resolver(model, serve_url, credential_bindings=None):
        return route.resolve_proposer(
            model, serve_url, credential_bindings,
            unified_roster=_roster, router_ledger=lambda: object())

    body, status, receipt, text, model_ref = route.openai_chat(
        {"model": "codex-cli", "messages": [{"role": "user", "content": "hi"}]},
        "http://127.0.0.1:8765",
        get_router_stats=lambda: None,
        flatten_messages=route.flatten_messages,
        resolve_proposer=resolver,
        chat_receipt=route.chat_receipt)

    assert status == 422
    assert body["error"]["code"] == "MODEL_SELECTION_REQUIRED"
    assert receipt is None and text is None and model_ref is None


def test_openai_chat_with_credentials_rejects_empty_codex_cli_model_before_bindings(monkeypatch):
    def fail_build_endpoints(**_kwargs):
        raise AssertionError("codex-cli provider construction should not start")

    class ExplodingBindings:
        def value_for(self, _slot):
            raise AssertionError("credential binding should not be resolved")

    monkeypatch.setattr(endpoints, "build_endpoints", fail_build_endpoints)

    def resolver(model, serve_url, credential_bindings=None):
        return route.resolve_proposer(
            model, serve_url, credential_bindings,
            unified_roster=_roster, router_ledger=lambda: object())

    body, status, receipt, text, model_ref = route.openai_chat(
        {"model": "codex-cli", "messages": [{"role": "user", "content": "hi"}]},
        "http://127.0.0.1:8765",
        credential_bindings=ExplodingBindings(),
        get_router_stats=lambda: None,
        flatten_messages=route.flatten_messages,
        resolve_proposer=resolver,
        chat_receipt=route.chat_receipt)

    assert status == 422
    assert body == {
        "schema": "flywheel.evidence-transport-error/v1",
        "error": {
            "code": "MODEL_SELECTION_REQUIRED",
            "message": "codex-cli requires an explicit model selection",
        },
    }
    assert receipt is None and text is None and model_ref is None


def test_guarded_gateway_json_preserves_model_selection_required_error():
    handler = object.__new__(gateway._Handler)
    handler.command = "POST"
    handler._gateway_guarded = True
    handler.wfile = bytearray()
    sent = {"code": None, "headers": []}
    handler.send_response = lambda code: sent.update(code=code)
    handler.send_header = lambda key, value: sent["headers"].append((key, value))
    handler._cors = lambda: None
    handler.end_headers = lambda: None

    class Writer:
        def __init__(self):
            self.data = b""
        def write(self, data):
            self.data += data

    writer = Writer()
    handler.wfile = writer
    body = {
        "schema": "flywheel.evidence-transport-error/v1",
        "error": {
            "code": "MODEL_SELECTION_REQUIRED",
            "message": "codex-cli requires an explicit model selection",
        },
    }

    handler._json(body, 422)

    assert sent["code"] == 422
    assert writer.data == b'{"schema": "flywheel.evidence-transport-error/v1", "error": {"code": "MODEL_SELECTION_REQUIRED", "message": "codex-cli requires an explicit model selection"}}'


def test_route_request_captures_supported_explicit_model_before_provider_call(monkeypatch):
    _codex_backend(monkeypatch)
    seen = {}

    def route_answer(prompt, endpoint, proposer, *, credential):
        inner = getattr(proposer, "inner", proposer)
        seen["prompt"] = prompt
        seen["endpoint"] = endpoint
        seen["model"] = inner.backend.model
        seen["credential"] = credential
        return {"ok": True}

    body, status = route.route_request(
        "hello", "codex-cli", "gpt-6-astra",
        unified_roster=_roster,
        router_ledger=lambda: object(),
        route_answer=route_answer)

    assert status == 200
    assert body == {"ok": True}
    assert seen == {
        "prompt": "hello",
        "endpoint": "codex-cli",
        "model": "gpt-6-astra",
        "credential": "cli-auth",
    }
