"""The stub model server answers the protocols the model lanes speak.

relay and local-model try ``127.0.0.1:8765`` first with the serve.py protocol
(``GET /health``, ``POST /generate``); the stub also answers the OpenAI-shaped
routes the plan names. The installed-app acceptance reads ``/stats`` to show a
run reached the stub and not some other model server on the host, so the
counts must move per request and must never hold prompt text.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from scripts import stub_model_server as stub


@pytest.fixture()
def server():
    srv = stub.start_in_thread("127.0.0.1", 0)
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", srv
    finally:
        srv.shutdown()
        srv.server_close()


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, json.loads(r.read())


def _post(url: str, raw: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=raw, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def test_health_answers_ok(server):
    base, _ = server
    status, body = _get(base + "/health")
    assert status == 200 and body["ok"] is True and body["model_ref"] == stub.MODEL_REF


def test_generate_answers_serve_shape_and_counts(server):
    base, srv = server
    status, body = _post(base + "/generate", json.dumps({
        "prompt": "user: say ok", "system": "s", "max_new_tokens": 8,
        "temperature": 0.0, "seed": 7}).encode())
    assert status == 200
    assert body == {"text": stub.REPLY_TEXT, "model_ref": stub.MODEL_REF, "seed": 7}
    assert srv.counts.snapshot()["generate"] == 1


def test_openai_routes_answer(server):
    base, srv = server
    status, models = _get(base + "/v1/models")
    assert status == 200 and models["data"][0]["id"] == stub.MODEL_REF
    status, body = _post(base + "/v1/chat/completions", json.dumps({
        "model": "x", "messages": [{"role": "user", "content": "hi"}]}).encode())
    assert status == 200 and body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == stub.REPLY_TEXT
    assert srv.counts.snapshot()["chat"] == 1


def test_stats_hold_counts_only(server):
    base, _ = server
    secret = "prompt-text-that-must-not-be-kept"
    _post(base + "/generate", json.dumps({"prompt": secret, "seed": 1}).encode())
    status, stats = _get(base + "/stats")
    assert status == 200
    assert all(isinstance(v, int) for v in stats["counts"].values())
    assert secret not in json.dumps(stats)


def test_bad_json_and_unknown_route(server):
    base, _ = server
    assert _post(base + "/generate", b"{not json")[0] == 400
    assert _post(base + "/generate", b"[1, 2]")[0] == 400
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(base + "/api/tags")
    assert err.value.code == 404


def test_refuses_a_non_loopback_host():
    with pytest.raises(ValueError):
        stub.make_server("0.0.0.0", 0)


def test_the_engine_serve_backend_talks_to_the_stub(server):
    base, _ = server
    from harness.local_agent import ServeBackend
    backend = ServeBackend(base_url=base)
    assert backend.health() is True
    reply = backend.chat([{"role": "user", "content": "say ok"}], system="s",
                         max_tokens=8, temperature=0.0, seed=3)
    assert reply["text"] == stub.REPLY_TEXT and reply["model_ref"] == stub.MODEL_REF


def test_the_relay_serve_backend_talks_to_the_stub(server, monkeypatch):
    from pathlib import Path
    relay_src = Path(__file__).resolve().parents[1] / "relay" / "src"
    if not (relay_src / "relay" / "local_agent.py").is_file():
        pytest.skip("relay submodule is not checked out")
    monkeypatch.syspath_prepend(str(relay_src))
    local_agent = pytest.importorskip("relay.local_agent")
    base, _ = server
    backend = local_agent.ServeBackend(base_url=base)
    assert backend.health() is True
    reply = backend.chat([{"role": "user", "content": "say ok"}], system="s",
                         max_tokens=8, temperature=0.0, seed=3)
    assert reply["text"] == stub.REPLY_TEXT and reply["model_ref"] == stub.MODEL_REF
