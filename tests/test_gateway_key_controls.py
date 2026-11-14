"""Budget controls on a virtual key: abandoned streams, calls in flight, pass-through.

  an abandoned stream     is charged for what was received and recorded with the amount
  calls in flight         are bounded per key, and reserve their output against the budget
  output per call         `max_tokens` has a per-key cap
(The pass-through allow-lists are in test_gateway_key_passthrough.py.)

A real gateway on a loopback port, a stub upstream, keys in the in-memory
store. No provider is called.
"""
import json
import socket
import threading
import time
from urllib.parse import urlparse

import pytest

from harness import gateway_key_cli, gateway_key_policy
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, MESSAGES, keyed, post, served, stream_bytes, turn2)

PATHS = ["/v1/messages", "/v1/responses"]


def _abandon(url: str, path: str, key: str) -> None:
    """Send a streamed request, read the first bytes of the reply, close the socket."""
    target = urlparse(url)
    payload = json.dumps({**BODIES[path], "stream": True}).encode()
    with socket.create_connection((target.hostname, target.port), timeout=10) as sock:
        sock.sendall(f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: "
                     f"application/json\r\nx-api-key: {key}\r\nContent-Length: "
                     f"{len(payload)}\r\n\r\n".encode() + payload)
        sock.recv(300)


def _settled(ledger, count: int) -> None:
    deadline = time.monotonic() + 10
    while len(ledger.entries) < count and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(ledger.entries) == count


def _caller(keys, name: str):
    from harness import gateway_key_gate
    row = keys.row(name)
    return gateway_key_gate.Caller(name, row["fingerprint"], row, keys)


@pytest.mark.parametrize("interface", ["messages", "responses"])
def test_an_abandoned_stream_is_charged_and_recorded_with_the_amount(
        keyed, monkeypatch, interface):
    """The stream is closed after its first text, as a client that leaves closes it."""
    from harness import gateway_messages, gateway_responses
    from harness.local_session import SessionLedger
    keys, _store = keyed
    keys.create("ci-bot")
    support.replayed(monkeypatch, "openai", streams=[stream_bytes("openai", "turn2")])
    ledger, path = SessionLedger(), "/v1/" + interface
    handle = gateway_messages.handle if interface == "messages" else gateway_responses.handle
    response = handle({**BODIES[path], "stream": True}, {}, ledger,
                      caller=_caller(keys, "ci-bot"))
    marks = (b"text_delta", b"output_text.delta")
    for chunk in response.chunks:
        if any(mark in chunk for mark in marks):
            break
    response.chunks.close()
    entry, = ledger.entries
    assert (entry.kind, entry.meta["reason"]) == ("endpoint_call_failed", "client_disconnected")
    assert entry.meta["key"] == "ci-bot" and entry.meta["estimated"] is True
    totals = keys.row("ci-bot")["totals"]
    assert entry.meta["charged_tokens"] == totals["tokens"]
    assert totals["input_tokens"] > 0 and totals["output_tokens"] > 0
    assert (totals["calls"], totals["estimated_calls"]) == (1, 1)


@pytest.mark.parametrize("path", PATHS)
def test_a_dropped_connection_is_charged_whichever_way_the_gateway_sees_it(
        keyed, served, path):
    """Over a real socket the gateway may finish writing before it sees the close.
    Either way the call has an entry and the key is charged."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served([support.stream_answer(stream_bytes("openai", "turn2"))])
    _abandon(url, path, raw)
    _settled(ledger, 1)
    entry = ledger.entries[0]
    assert entry.kind in ("endpoint_call", "endpoint_call_failed")
    assert entry.meta["charged_tokens"] > 0
    assert keys.row("ci-bot")["totals"]["tokens"] == entry.meta["charged_tokens"]


def test_a_key_that_drops_every_stream_runs_out_of_budget(keyed, served):
    """The reviewer's case: three dropped streams on a 10-token key were all free."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=3)
    url, upstream, ledger = served([support.stream_answer(stream_bytes("openai", "turn2"))] * 3)
    _abandon(url, "/v1/messages", raw)
    _settled(ledger, 1)
    assert keys.row("ci-bot")["totals"]["tokens"] >= 3
    status, _headers, body = post(url, "/v1/messages", raw)
    assert status == 400 and "token limit" in body["error"]["message"]
    assert len(upstream.requests) == 1, "the next call reaches no upstream"


def test_a_cut_anthropic_stream_is_charged_the_input_the_provider_reported(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served(
        [support.stream_answer(support.raw("upstream/anthropic_cut.sse"))], provider="anthropic")
    status, _headers, body = post(url, "/v1/messages", raw, {**MESSAGES, "stream": True})
    assert status == 200 and b"event: error" in body
    entry, = ledger.entries
    assert entry.meta["reason"] == "stream_incomplete" and entry.meta["estimated"] is True
    assert b'"input_tokens":468' in support.raw("upstream/anthropic_cut.sse")
    assert keys.row("ci-bot")["totals"]["input_tokens"] == 468
    assert entry.meta["charged_tokens"] == keys.row("ci-bot")["totals"]["tokens"]


def test_the_owner_is_not_charged_for_an_abandoned_stream(monkeypatch):
    from harness import gateway_messages
    from harness.local_session import SessionLedger
    support.replayed(monkeypatch, "openai", streams=[stream_bytes("openai", "turn2")])
    ledger = SessionLedger()
    response = gateway_messages.handle({**MESSAGES, "stream": True}, {}, ledger)
    next(response.chunks)
    response.chunks.close()
    entry, = ledger.entries
    assert entry.meta["reason"] == "client_disconnected" and entry.meta["key"] == "owner"
    assert "charged_tokens" not in entry.meta


class _Gate:
    """Hold every upstream request until `open` is set."""

    def __init__(self, monkeypatch):
        self.open, self.waiting = threading.Event(), 0
        real, gate = support.Upstream.__init__, self

        def patched(stub, answers):
            real(stub, answers)
            handler = stub.server.RequestHandlerClass
            inner = handler.do_POST

            def do_post(request):
                gate.waiting += 1
                gate.open.wait(20)
                inner(request)
            handler.do_POST = do_post
        monkeypatch.setattr(support.Upstream, "__init__", patched)


def _parallel(url, path, raw, count: int, gate: _Gate, expect_upstream: int) -> list:
    got = []

    def one():
        got.append(post(url, path, raw))
    threads = [threading.Thread(target=one) for _ in range(count)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + 10
    while (gate.waiting < expect_upstream or len(got) < count - expect_upstream) \
            and time.monotonic() < deadline:
        time.sleep(0.02)
    gate.open.set()
    for thread in threads:
        thread.join()
    return got


@pytest.mark.parametrize("path", PATHS)
def test_calls_in_flight_on_one_key_are_bounded(keyed, served, monkeypatch, path):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    keys.mark("ci-bot", in_flight=2)
    gate = _Gate(monkeypatch)
    url, upstream, ledger = served(turn2(6))
    got = _parallel(url, path, raw, 6, gate, 2)
    statuses = sorted(status for status, _h, _b in got)
    assert statuses == [200, 200, 429, 429, 429, 429]
    assert len(upstream.requests) == 2, "only the in-flight limit reached the upstream"
    refused = next((h, b) for status, h, b in got if status == 429)
    assert "in flight" in refused[1]["error"]["message"]
    assert {k.lower(): v for k, v in refused[0].items()}["retry-after"] == "1"
    assert post(url, path, raw)[0] == 200, "the slots are free again afterwards"


def test_parallel_calls_cannot_multiply_past_a_token_limit(keyed, served, monkeypatch):
    """The reviewer's case: one token left, twelve calls, ten were served."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=461)
    keys.debit("ci-bot", {"input": 460})
    gate = _Gate(monkeypatch)
    url, upstream, _ledger = served(turn2(12))
    got = _parallel(url, "/v1/messages", raw, 12, gate, 1)
    assert sorted(status for status, _h, _b in got) == [200] + [429] * 11
    assert len(upstream.requests) == 1
    assert keys.row("ci-bot")["totals"]["tokens"] == 920, "one call crossed, by its own cost"


def test_control_the_default_in_flight_limit_admits_four(keyed, served, monkeypatch):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    gate = _Gate(monkeypatch)
    url, upstream, _ledger = served(turn2(5))
    got = _parallel(url, "/v1/messages", raw, 5, gate, gateway_key_policy.DEFAULT_IN_FLIGHT)
    assert sorted(status for status, _h, _b in got) == [200, 200, 200, 200, 429]


def test_the_owner_has_no_in_flight_limit(keyed, served, monkeypatch):
    gate = _Gate(monkeypatch)
    url, upstream, _ledger = served(turn2(6))
    got = _parallel(url, "/v1/messages", support.TOKEN, 6, gate, 6)
    assert [status for status, _h, _b in got] == [200] * 6


@pytest.mark.parametrize("path, field", [("/v1/messages", "max_tokens"),
                                         ("/v1/responses", "max_output_tokens")])
def test_a_key_caps_the_output_one_call_may_ask_for(keyed, served, path, field):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    keys.mark("ci-bot", max_output=100)
    url, upstream, _ledger = served(turn2(1))
    status, _headers, body = post(url, path, raw, {**BODIES[path], field: 101})
    assert status == 400 and field in body["error"]["message"]
    assert "100" in body["error"]["message"] and upstream.requests == []
    assert post(url, path, raw, {**BODIES[path], field: 100})[0] == 200


def test_the_cli_sets_and_shows_the_controls(keyed, capsys):
    keys, store = keyed
    environ = {"FLYWHEEL_HOME": str(keys.path.parent)}

    def run(*argv) -> int:
        return gateway_key_cli.main(list(argv), store=store, environ=environ)
    assert run("create", "ci-bot", "--in-flight", "2", "--max-output", "8000") == 0
    assert run("set", "ci-bot", "--allow-beta", "a-beta,b-beta", "--allow-server-tool",
               "web_search", "--allow-mcp") == 0
    row = keys.row("ci-bot")
    assert (row["in_flight"], row["max_output"], row["mcp"]) == (2, 8000, True)
    assert row["betas"] == ["a-beta", "b-beta"] and row["server_tools"] == ["web_search"]
    capsys.readouterr()
    assert run("show", "ci-bot") == 0
    shown = capsys.readouterr().out
    for text in ("in flight     2", "max output    8000", "a-beta, b-beta", "web_search"):
        assert text in shown
    assert run("set", "ci-bot", "--in-flight", "0") == 1
    assert "--in-flight" in capsys.readouterr().err
