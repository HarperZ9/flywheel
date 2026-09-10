"""Synthetic HTTP regressions for private agent-run history reads."""
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from harness import gateway
from harness.eval_store import save_agent_run

TOKEN = "synthetic-reader-test-token"


@pytest.fixture
def history_server(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    saved = save_agent_run(root, {"final": "fixture run", "events": []})
    (root / "outside.json").write_text(
        '{"marker":"OUTSIDE_FIXTURE_ONLY"}', encoding="utf-8")

    class Handler(gateway._Handler):
        auth_token = TOKEN
        flywheel_home = tmp_path / "home"
        def log_message(self, *_args):
            pass

    Handler.root, Handler.run_root = tmp_path, root
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, *, token=TOKEN, host=None):
        headers = {} if token is None else {"Authorization": "Bearer " + token}
        if host is not None:
            headers["Host"] = host
        conn = HTTPConnection("127.0.0.1", server.server_port, timeout=20)
        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    yield Handler, root, saved["run_id"], request
    server.shutdown()
    server.server_close()
    thread.join(timeout=20)


@pytest.mark.parametrize("route", ["/api/agent/runs", "/api/agent/run?id=" + "0" * 16])
@pytest.mark.parametrize("mode", ["off", "missing", "wrong", "host"])
def test_history_requires_owner_even_with_auth_off(history_server, route, mode):
    handler, _, _, request = history_server
    if mode == "off":
        handler.auth_token = ""
    status, body = request(route, token=None if mode in {"off", "missing"} else (
        "incorrect" if mode == "wrong" else TOKEN),
        host="untrusted.invalid" if mode == "host" else None)
    assert status == 401
    assert body["error"]["code"] == "AUTH_REQUIRED"
    assert not (handler.flywheel_home / "state").exists()


@pytest.mark.parametrize("query", [
    "id=../outside", "id=..%2Foutside", "id=..%5Coutside", "id=C%3Aoutside",
    "id=", "id=" + "a" * 17, "id=" + "a" * 16 + "%00", "id=%252e%252e%252foutside",
    "id=" + "a" * 16 + "&id=" + "b" * 16, "id=" + "a" * 16 + "&extra=1",
])
def test_invalid_ids_are_typed_400_without_content(history_server, query):
    _, _, _, request = history_server
    status, body = request("/api/agent/run?" + query)
    assert status == 400
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert "OUTSIDE_FIXTURE_ONLY" not in json.dumps(body)
    assert "outside" not in json.dumps(body)


def test_valid_detail_list_and_missing_status(history_server):
    _, _, rid, request = history_server
    status, body = request("/api/agent/run?id=" + rid.upper())
    assert status == 200 and body["intact"] is True and body["final"] == "fixture run"
    status, body = request("/api/agent/runs?limit=1")
    assert status == 200 and body["runs"][0]["run_id"] == rid
    status, body = request("/api/agent/run?id=" + "0" * 16)
    assert status == 404 and body["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=-1", "limit=x", "limit=1&limit=2"])
def test_invalid_list_limits_are_bounded(history_server, query):
    _, _, _, request = history_server
    status, body = request("/api/agent/runs?" + query)
    assert status == 400 and body["error"]["code"] == "INVALID_REQUEST"


def test_oversized_and_malformed_history_do_not_leak(history_server):
    _, root, rid, request = history_server
    path = root / "agent_runs" / (rid + ".json")
    path.write_bytes(b"x" * (1_048_576 + 1))
    status, body = request("/api/agent/run?id=" + rid)
    assert status == 413 and body["error"]["code"] == "TOO_LARGE"
    path.write_text('{"final":"duplicate","final":"other"}', encoding="utf-8")
    status, body = request("/api/agent/run?id=" + rid)
    assert status == 422 and body["error"]["code"] == "UNREADABLE"
    assert "duplicate" not in json.dumps(body)


def test_stored_error_is_content_not_transport_failure(history_server):
    _, root, _, request = history_server
    doc = {"error": {"code": "TOO_LARGE"}, "final": "retained failed attempt"}
    rid = save_agent_run(root, doc)["run_id"]
    status, body = request("/api/agent/run?id=" + rid)
    assert status == 200 and body["intact"] is True
    assert body["error"] == doc["error"]
