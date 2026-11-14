"""A client that leaves early, or sends its body late, does not escape the record.

Three behaviours, each over real loopback sockets against a stub upstream:

  reset before the headers   a client that resets its connection while the
                             upstream is still opening a stream leaves a
                             ledger entry and a charge, marked abandoned
  body after the headers     a key's limits are read again after the request
                             body arrived, so requests that send headers first
                             and bodies later cannot all pass on one stale row
  a silent connection        the gateway closes a connection that sends
                             nothing for the read timeout

No provider is called.
"""
import json
import os
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

from harness import gateway_interfaces, gateway_read_timeout
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, MESSAGES, TURN2_TOKENS, keyed, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

PATHS = ["/v1/messages", "/v1/responses"]
# struct linger {on, seconds 0}: two shorts on Windows, two ints elsewhere
_LINGER_NOW = struct.pack("hh" if os.name == "nt" else "ii", 1, 0)


def _head(path: str, key: str, length: int) -> bytes:
    return (f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
            f"x-api-key: {key}\r\nContent-Length: {length}\r\n\r\n").encode()


def _status(sock) -> int:
    data = b""
    while b"\r\n\r\n" not in data:
        more = sock.recv(65536)
        if not more:
            break
        data += more
    return int(data.split(b" ", 2)[1]) if data else 0


def _settled(ledger, count: int) -> None:
    deadline = time.monotonic() + 10
    while len(ledger.entries) < count and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(ledger.entries) == count


def _caller(keys, name: str):
    from harness import gateway_key_gate
    row = keys.row(name)
    return gateway_key_gate.Caller(name, row["fingerprint"], row, keys)


# --- a reset before the response headers ---------------------------------------------

class _Gone:
    """A handler whose client reset the connection before the headers left."""
    close_connection = False
    wfile = None

    def send_response(self, *args):
        pass

    def send_header(self, *args):
        pass

    def _cors(self):
        pass

    def end_headers(self):
        raise ConnectionResetError("the peer reset the connection before the headers")


def _abandoned(entry, keys) -> None:
    assert (entry.kind, entry.meta["reason"]) == ("endpoint_call_failed", "client_disconnected")
    assert entry.meta["abandoned"] is True and entry.meta["estimated"] is True
    assert entry.meta["key"] == "ci-bot" and entry.meta["charged_tokens"] > 0
    totals = keys.row("ci-bot")["totals"]
    assert totals["tokens"] == entry.meta["charged_tokens"]
    assert (totals["calls"], totals["estimated_calls"]) == (1, 1)


@pytest.mark.parametrize("interface", ["messages", "responses"])
def test_a_stream_whose_headers_never_left_is_recorded_and_charged(
        keyed, monkeypatch, interface):
    """The chunk generator never starts, so only the explicit close hook can record it."""
    from harness import gateway_messages, gateway_responses
    from harness.local_session import SessionLedger
    keys, _store = keyed
    keys.create("ci-bot")
    support.replayed(monkeypatch, "openai", streams=[stream_bytes("openai", "turn2")])
    ledger, path = SessionLedger(), "/v1/" + interface
    handle = gateway_messages.handle if interface == "messages" else gateway_responses.handle
    response = handle({**BODIES[path], "stream": True}, {}, ledger,
                      caller=_caller(keys, "ci-bot"))
    gateway_interfaces.send(_Gone(), response)      # the reset is logged, not raised
    entry, = ledger.entries
    _abandoned(entry, keys)


def test_control_a_stream_that_is_read_to_its_end_is_recorded_once(keyed, monkeypatch):
    """The close hook runs after every stream; it must not add a second entry."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    from harness import gateway_messages
    from harness.local_session import SessionLedger
    support.replayed(monkeypatch, "openai", streams=[stream_bytes("openai", "turn2")])
    ledger = SessionLedger()
    response = gateway_messages.handle({**MESSAGES, "stream": True}, {}, ledger,
                                       caller=_caller(keys, "ci-bot"))

    class Sink(_Gone):
        wfile = type("W", (), {"write": lambda self, data: None, "flush": lambda self: None})()

        def end_headers(self):
            pass
    gateway_interfaces.send(Sink(), response)
    assert support.kinds(ledger) == ["endpoint_call"]
    assert "abandoned" not in ledger.entries[0].meta
    assert keys.row("ci-bot")["totals"]["tokens"] == TURN2_TOKENS


@pytest.mark.parametrize("path", PATHS)
def test_a_client_that_resets_while_the_upstream_is_opening_is_charged(
        keyed, monkeypatch, tmp_path, path):
    """Real sockets: the reset arrives before the upstream has answered."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    seen, payload = [], stream_bytes("openai", "turn2")

    class Slow(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            seen.append(self.path)
            time.sleep(0.6)                     # the client is gone before this ends
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    try:
        with support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
            support.point_at(monkeypatch, "openai",
                             f"http://127.0.0.1:{upstream.server_address[1]}")
            target = urlparse(url)
            body = json.dumps({**BODIES[path], "stream": True}).encode()
            sock = socket.create_connection((target.hostname, target.port), timeout=10)
            sock.sendall(_head(path, raw, len(body)) + body)
            time.sleep(0.2)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, _LINGER_NOW)
            sock.close()                        # an abortive close: the peer sees a reset
            _settled(ledger, 1)
            assert len(seen) == 1, "the provider was called once"
            _abandoned(ledger.entries[0], keys)
    finally:
        upstream.shutdown()
        upstream.server_close()


# --- headers first, bodies later ------------------------------------------------------

def test_requests_that_send_bodies_late_are_checked_against_the_totals_as_they_are(
        keyed, served):
    """Limit 400, one call costs 460. Documented margin: one call may cross the limit
    by its own cost, and the next call is refused. Six requests that all sent their
    headers while the key was under its limit were once all served."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=400)
    count = 6
    url, upstream, ledger = served(turn2(count))
    target, payload = urlparse(url), json.dumps(MESSAGES).encode()
    socks = []
    for _ in range(count):
        sock = socket.create_connection((target.hostname, target.port), timeout=10)
        sock.sendall(_head("/v1/messages", raw, len(payload)))
        socks.append(sock)
    time.sleep(0.5)                             # every request is past the credential check
    statuses = []
    for sock in socks:                          # one at a time: never two in flight
        sock.sendall(payload)
        statuses.append(_status(sock))
        sock.close()
    assert statuses == [200] + [400] * (count - 1)
    assert len(upstream.requests) == 1, "five requests reached no upstream"
    assert keys.row("ci-bot")["totals"]["tokens"] == TURN2_TOKENS
    assert support.kinds(ledger) == ["endpoint_call"] + ["endpoint_call_refused"] * (count - 1)


@pytest.mark.parametrize("change", ["revoke", "suspend"])
def test_a_key_stopped_between_headers_and_body_is_refused(keyed, served, change):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, _ledger = served(turn2(1))
    target, payload = urlparse(url), json.dumps(MESSAGES).encode()
    with socket.create_connection((target.hostname, target.port), timeout=10) as sock:
        sock.sendall(_head("/v1/messages", raw, len(payload)))
        time.sleep(0.3)
        if change == "revoke":
            keys.revoke("ci-bot")
        else:
            keys.mark("ci-bot", suspended={"reason": "delivered_unrecorded_charge", "at": 1})
        sock.sendall(payload)
        assert _status(sock) == (401 if change == "revoke" else 403)
    assert upstream.requests == []


def test_control_sequential_requests_on_the_same_key(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=400)
    url, upstream, _ledger = served(turn2(3))
    assert [post(url, "/v1/messages", raw)[0] for _ in range(3)] == [200, 400, 400]
    assert len(upstream.requests) == 1


# --- the read timeout -----------------------------------------------------------------

def test_the_read_timeout_has_a_default_and_a_switch():
    assert gateway_read_timeout.DEFAULT == 30.0
    assert gateway_read_timeout.seconds({}) == 30.0
    assert gateway_read_timeout.seconds({gateway_read_timeout.ENV: "2.5"}) == 2.5
    assert gateway_read_timeout.seconds({gateway_read_timeout.ENV: "0"}) is None
    assert gateway_read_timeout.seconds({gateway_read_timeout.ENV: "off"}) is None
    assert gateway_read_timeout.seconds({gateway_read_timeout.ENV: "soon"}) == 30.0


@pytest.mark.parametrize("path", PATHS)
def test_a_body_that_never_arrives_is_answered_408_and_reaches_no_upstream(
        keyed, served, monkeypatch, path):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    monkeypatch.setenv(gateway_read_timeout.ENV, "0.4")
    url, upstream, ledger = served(turn2(1))
    target = urlparse(url)
    started = time.monotonic()
    with socket.create_connection((target.hostname, target.port), timeout=10) as sock:
        sock.sendall(_head(path, raw, 500))     # 500 bytes are promised and never sent
        assert _status(sock) == 408
    assert time.monotonic() - started < 5
    assert upstream.requests == [] and ledger.entries == []


def test_a_connection_that_sends_nothing_is_closed(keyed, served, monkeypatch):
    monkeypatch.setenv(gateway_read_timeout.ENV, "0.4")
    url, upstream, _ledger = served(turn2(1))
    target = urlparse(url)
    started = time.monotonic()
    with socket.create_connection((target.hostname, target.port), timeout=10) as sock:
        assert sock.recv(100) == b"", "the gateway closed the silent connection"
    assert time.monotonic() - started < 5 and upstream.requests == []


def test_control_a_prompt_request_is_served_under_the_timeout(keyed, served, monkeypatch):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    monkeypatch.setenv(gateway_read_timeout.ENV, "0.4")
    url, upstream, _ledger = served(turn2(1))
    assert post(url, "/v1/messages", raw)[0] == 200 and len(upstream.requests) == 1


def test_a_close_hook_that_fails_is_logged_with_its_cause(caplog):
    """The client has gone by then, so the failure must reach the log."""
    from harness.gateway_turn import Response

    def broken():
        raise OSError("the ledger file is gone")
    response = Response(200, chunks=(chunk for chunk in ()), close=broken)
    with caplog.at_level("ERROR", logger="harness.gateway_interfaces"):
        gateway_interfaces.send(_Gone(), response)
    assert "could not be closed and recorded (OSError): the ledger file is gone" in caplog.text
