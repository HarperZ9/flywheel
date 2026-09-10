"""Response evidence survives backend rejection without a second request."""
import json

import pytest

from harness.bulletin_model_call import CallError, OneGenerationTransport, execute_backend_once
from harness.bulletin_model_exchange import PrivateExchange
from harness.local_agent import OllamaBackend, MalformedBackendOutput


def request(tokens=32):
    return json.dumps({"model": "fixture", "messages": [], "stream": False,
                       "options": {"num_predict": tokens}}).encode()


def transport(store, responses, stage="readiness"):
    calls = []
    def fake(method, url, body, timeout):
        calls.append((method, url, body, timeout))
        return 200, responses
    return OneGenerationTransport(fake, store, reservation_id="campaign-readiness",
        stage_id=stage, origin="http://127.0.0.1:9999", model="fixture", max_tokens=32), calls


def test_readiness_capture_has_text_and_typed_usage(tmp_path):
    response = {"model": "fixture", "message": {"content": "exact é\n"}, "eval_count": 3}
    with PrivateExchange.create(tmp_path / "run") as store:
        call, calls = transport(store, response)
        assert call("POST", "http://127.0.0.1:9999/api/chat", request(), 60)[1] == response
        saved = json.loads(store.read("response.json", max_bytes=2 * 1024 * 1024))
        assert saved["capture_kind"] == "parsed_response_not_wire"
        assert saved["parsed_response"] == response
        assert saved["usage"] == {"eval_count": 3}
        assert store.read("assistant.txt", max_bytes=100) == b"exact \xc3\xa9\n"
        assert len(calls) == 1
        with pytest.raises(CallError):
            call("POST", "http://127.0.0.1:9999/api/chat", request(), 60)
        assert len(calls) == 1


def test_backend_identity_failure_keeps_received_text(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        call, calls = transport(store, {"model": "other", "message": {"content": "wrong identity"}, "eval_count": 8})
        backend = OllamaBackend(base_url="http://127.0.0.1:9999", model="fixture", transport=call)
        with pytest.raises(MalformedBackendOutput):
            backend.chat([], system="", max_tokens=32, temperature=0.2, seed=101)
        assert store.read("assistant.txt", max_bytes=100) == b"wrong identity"
        assert len(calls) == 1


def test_malformed_text_and_bool_usage_are_not_coerced(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        call, _ = transport(store, {"message": {"content": 17}, "eval_count": True})
        call("POST", "http://127.0.0.1:9999/api/chat", request(), 60)
        saved = json.loads(store.read("response.json", max_bytes=2097152))
        assert saved["parsed_response"]["message"]["content"] == 17
        assert saved["assistant_text_state"] == "invalid_or_missing"
        assert "eval_count" not in saved["usage"]
        assert "native_usage_refused" in saved["usage"]


def test_capture_failure_after_response_is_sticky(tmp_path, monkeypatch):
    with PrivateExchange.create(tmp_path / "run") as store:
        call, calls = transport(store, {"message": {"content": "received"}})
        original = store.put
        def fail(name, *args, **kwargs):
            if name == "response.json":
                raise OSError("disk")
            return original(name, *args, **kwargs)
        monkeypatch.setattr(store, "put", fail)
        with pytest.raises(CallError):
            call("POST", "http://127.0.0.1:9999/api/chat", request(), 60)
        assert call.failed and call.response_received
        monkeypatch.setattr(store, "put", original)
        with pytest.raises(CallError):
            call("GET", "http://127.0.0.1:9999/api/tags", None, 5)
        assert len(calls) == 1


@pytest.mark.parametrize("method,url,body", [
    ("POST", "http://127.0.0.1:9998/api/chat", request()),
    ("POST", "http://127.0.0.1:9999/api/chat?extra=1", request()),
    ("POST", "http://127.0.0.1:9999/api/chat", request(33)),
    ("POST", "http://127.0.0.1:9999/api/chat", request(True)),
    ("DELETE", "http://127.0.0.1:9999/api/chat", None),
])
def test_scope_and_token_bound_rejected_before_io(tmp_path, method, url, body):
    with PrivateExchange.create(tmp_path / "run") as store:
        call, calls = transport(store, {})
        with pytest.raises(CallError):
            call(method, url, body, 60)
        assert calls == []


def test_smoke_and_actor_cannot_probe_health(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        call, calls = transport(store, {}, stage="smoke")
        with pytest.raises(CallError):
            call("GET", "http://127.0.0.1:9999/api/tags", None, 5)
        assert calls == []


def test_gate_cannot_promote_non_string_capture_with_str_coercion(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        call, calls = transport(store, {"model": "fixture", "message": {"content": 17}})
        def gate():
            call("POST", "http://127.0.0.1:9999/api/chat", request(), 60)
            return {"verdict": "MODEL_ENDPOINT_GATE_PASS"}
        result = execute_backend_once(call, gate)
        assert result["backend_valid"] is False and result["text"] is None
        assert result["failure"] == "invalid_assistant_text"
        assert result["backend_result"]["verdict"] == "MODEL_ENDPOINT_GATE_PASS"
        assert len(calls) == 1


def test_backend_rejection_retains_text_but_is_not_admitted(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        call, calls = transport(store, {"model": "wrong", "message": {"content": "raw"}})
        backend = OllamaBackend(base_url="http://127.0.0.1:9999", model="fixture", transport=call)
        result = execute_backend_once(call, lambda: backend.chat([], system="", max_tokens=32, temperature=0.2, seed=1))
        assert result["text"] == "raw" and result["backend_valid"] is False
        assert result["failure"] == "MalformedBackendOutput"
        assert len(calls) == 1


@pytest.mark.parametrize("observed,expected", [("wrong", False), ("fixture", True)])
def test_actual_gate_disposition_is_respected(tmp_path, observed, expected):
    from harness.model_endpoint_gate_cli import probe_profile
    from tests.model_endpoint_gate_fixtures import profile
    row = profile("ollama")
    row.update(endpoint_url="http://127.0.0.1:9999", model_ref="ollama:fixture", selectors=["fixture"])
    calls = []
    def fake(method, url, body, timeout):
        calls.append(method)
        if method == "GET":
            return 200, {"models": [{"name": "fixture", "digest": "sha256:abc"}]}
        return 200, {"model": observed, "message": {"content": "captured"}, "eval_count": 1}
    with PrivateExchange.create(tmp_path / "run") as store:
        call = OneGenerationTransport(fake, store, reservation_id="campaign-readiness",
            stage_id="readiness", origin=row["endpoint_url"], model="fixture", max_tokens=32)
        result = execute_backend_once(call, lambda: probe_profile(row, prompt="ready",
            timeout_seconds=60, max_tokens=32, seed=1, transport=call))
        assert result["backend_valid"] is expected
        assert result["text"] == "captured"
        assert calls == ["GET", "POST"]
