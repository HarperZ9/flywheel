"""Acquisition controls independent of acting-client write responses."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

from harness.bulletin_observer import observe_handoff
from harness.bulletin_task_contract import evaluate_handoff
from test_bulletin_task_contract import fixture


@pytest.fixture
def board():
    c, o = fixture()
    state = {"posts": o["posts"], "source": o["source"], "mode": "normal", "calls": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            state["calls"] += 1
            if state["mode"] == "redirect":
                self.send_response(302)
                self.send_header("Location", "/canary")
                self.end_headers()
                return
            is_feed = self.path.startswith("/v1/feed")
            payload = ({"ok": True, "posts": state["posts"], "next_before": None}
                       if is_feed else {"ok": True, "post": state["source"]})
            if state["mode"] == "pagination" and is_feed:
                payload["next_before"] = payload["posts"][-1]["id"]
            if state["mode"] == "missing_cursor" and is_feed:
                del payload["next_before"]
            if state["mode"] == "changed" and is_feed and state["calls"] >= 3:
                payload = deepcopy(payload)
                payload["posts"][0]["body"] = "changed"
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield c, state, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_real_http_readback_and_anchor(board):
    c, state, base = board
    o = observe_handoff(c, base, allow_loopback=True)
    assert o["gaps"] == []
    assert state["calls"] == 3
    assert evaluate_handoff(c, o)["verdict"] == "PASS"
    assert o["acquisition"]["request_count"] == 3


@pytest.mark.parametrize(("mode", "gap"), [
    ("redirect", "read_failed"), ("pagination", "pagination_invalid"),
    ("changed", "snapshot_changed"),
    ("missing_cursor", "pagination_metadata_missing"),
])
def test_missing_and_changed_observation_is_not_success(board, mode, gap):
    c, state, base = board
    state["mode"] = mode
    o = observe_handoff(c, base, allow_loopback=True)
    assert gap in o["gaps"]
    assert evaluate_handoff(c, o)["verdict"] != "PASS"
    if mode == "redirect":
        assert state["calls"] <= 3  # No redirected canary requests.


def test_oversized_body_is_rejected(board):
    c, _, base = board
    c["max_response_bytes"] = 30
    o = observe_handoff(c, base, allow_loopback=True)
    assert "read_failed" in o["gaps"]
    assert evaluate_handoff(c, o)["verdict"] == "UNVERIFIABLE"


def test_http_requires_explicit_loopback_admission(board):
    c, _, base = board
    with pytest.raises(ValueError):
        observe_handoff(c, base)


def test_page_exhaustion_is_explicit(board):
    c, state, base = board
    c["max_pages"] = 1
    state["mode"] = "pagination"
    assert "page_limit" in observe_handoff(c, base, allow_loopback=True)["gaps"]
