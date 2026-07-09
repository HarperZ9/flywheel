"""Messages-API facade falsifier (F1) — compatibility PLUS a receipt per turn.

Properties: request flattens correctly; response is valid Anthropic Messages
shape; every turn carries a content-addressed receipt binding request+response;
frontier tier names alias to the served model (never 404); errors are typed
(never 200-empty).
"""
import io
import json

import pytest

from harness.messages_api import (
    translate_request, translate_response, make_receipt, resolve_model,
    error_response)
from harness import serve

REQ = {
    "model": "claude-fable-5",
    "system": "You are a code generator.",
    "messages": [{"role": "user", "content": "Implement add(a, b)."}],
    "max_tokens": 64, "temperature": 0.0,
}
GEN = {"text": "def add(a, b):\n    return a + b\n", "model_ref": "14b-adapter",
       "seed": 0, "prompt_hash": "abc123"}


def test_request_flattens_messages_and_system():
    p = translate_request(REQ)
    assert "Implement add(a, b)." in p["prompt"]
    assert p["system"] == "You are a code generator."
    assert p["max_new_tokens"] == 64 and p["requested_model"] == "claude-fable-5"


def test_malformed_request_raises_for_typed_error():
    with pytest.raises(ValueError):
        translate_request({"messages": []})


def test_response_is_valid_messages_shape_with_receipt():
    p = translate_request(REQ)
    resp = translate_response(GEN, p, served_ref="14b-adapter")
    assert resp["type"] == "message" and resp["role"] == "assistant"
    assert resp["content"][0]["type"] == "text"
    assert "def add" in resp["content"][0]["text"]
    assert resp["model"] == "claude-fable-5"          # echoes requested name
    assert resp["x_receipt"]["model_ref"] == "14b-adapter"  # records the truth
    assert resp["id"].startswith("msg_")


def test_receipt_binds_request_and_response():
    p = translate_request(REQ)
    r1 = make_receipt(p, GEN, "14b-adapter")
    r2 = make_receipt(p, GEN, "14b-adapter")
    assert r1["receipt_id"] == r2["receipt_id"]        # idempotent
    # a different response -> a different receipt id
    r3 = make_receipt(p, {**GEN, "text": "def add(a,b): return a*b"}, "14b-adapter")
    assert r3["receipt_id"] != r1["receipt_id"]


def test_frontier_tier_names_alias_to_served_model():
    for name in ("claude-opus-4-8", "claude-sonnet-5", "gpt-5.6", "claude-fable-5"):
        assert resolve_model(name, "14b-adapter") == "14b-adapter"
    assert resolve_model("my-custom-model", "14b-adapter") == "my-custom-model"


def test_error_is_typed_not_empty():
    e = error_response("bad request")
    assert e["type"] == "error" and e["error"]["message"] == "bad request"


def test_serve_messages_route_translates_and_sets_receipt(monkeypatch):
    class Handler(serve._H):
        def __init__(self):
            self.path = "/v1/messages"
            self.headers = {"Content-Length": str(len(body))}
            self.rfile = io.BytesIO(body)
            self.wfile = io.BytesIO()
            self.status = None
            self.sent_headers = {}

        def send_response(self, code, message=None):
            self.status = code

        def send_header(self, key, value):
            self.sent_headers[key] = value

        def end_headers(self):
            pass

    def fake_generate(prompt, max_new_tokens, temperature, top_p, seed, system):
        assert "Implement add" in prompt
        assert system == "You are a code generator."
        return GEN

    monkeypatch.setattr(serve, "MODEL_REF", "14b-adapter")
    monkeypatch.setattr(serve, "generate", fake_generate)
    body = json.dumps(REQ).encode()

    h = Handler()
    h.do_POST()

    assert h.status == 200
    payload = json.loads(h.wfile.getvalue())
    assert payload["type"] == "message"
    assert payload["model"] == "claude-fable-5"
    assert payload["x_receipt"]["model_ref"] == "14b-adapter"
    assert h.sent_headers["X-Receipt-Id"] == payload["x_receipt"]["receipt_id"]


def test_serve_messages_route_returns_typed_error_for_bad_request():
    class Handler(serve._H):
        def __init__(self):
            self.path = "/v1/messages"
            self.headers = {"Content-Length": str(len(body))}
            self.rfile = io.BytesIO(body)
            self.wfile = io.BytesIO()
            self.status = None

        def send_response(self, code, message=None):
            self.status = code

        def send_header(self, key, value):
            pass

        def end_headers(self):
            pass

    body = json.dumps({"messages": []}).encode()

    h = Handler()
    h.do_POST()

    assert h.status == 400
    payload = json.loads(h.wfile.getvalue())
    assert payload["type"] == "error"
    assert payload["error"]["type"] == "invalid_request_error"
