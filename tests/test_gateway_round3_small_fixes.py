"""Gateway items of the independent review of 2.0.0, each with its control.

  D1  an unfinished stream on an OpenAI-format upstream was charged a word
      count of the prompt: 80,000 characters with no space cost 6 tokens. The
      charge is now at least a quarter of the characters, rounded up.
  A2  the key's row was read again outside the admission lock, so a request
      paused between the read and its admission was admitted on a stale
      total. The read and the admission are one step under one lock.
  N3  a client with no credential that dripped header bytes held a thread for
      as long as it liked. The head of a request has one deadline, and the
      body of a model call has one.
  N5  `gateway-ledger show` printed a 5,000 character field whole. A field is
      cut at 80 characters unless `--full` is given.

A real gateway on a loopback port with a stub upstream. No provider is called.
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

from harness import gateway_key_policy, gateway_ledger, gateway_ledger_cli, gateway_read_timeout
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    MESSAGES, TURN2_TOKENS, keyed, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

_LINGER_NOW = struct.pack("hh" if os.name == "nt" else "ii", 1, 0)


def _head(path, key, length, extra=""):
    credential = f"x-api-key: {key}\r\n" if key else ""
    return (f"POST {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
            f"{credential}{extra}Content-Length: {length}\r\n\r\n").encode()


def _status(sock) -> int:
    data = b""
    while b"\r\n\r\n" not in data:
        more = sock.recv(65536)
        if not more:
            break
        data += more
    return int(data.split(b" ", 2)[1]) if data else 0


# --- D1 -------------------------------------------------------------------------------

PROMPTS = {"base64": ("QUJD" * 20000, 20000),              # 80,000 characters, no space
           "cjk": ("\u6f22\u5b57" * 4000, 2000)}            # 8,000 CJK characters


@pytest.mark.parametrize("kind", list(PROMPTS))
def test_an_unfinished_openai_stream_is_charged_a_quarter_of_the_prompts_characters(
        keyed, monkeypatch, tmp_path, kind):
    prompt, least = PROMPTS[kind]
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=1000)
    payload, seen = stream_bytes("openai", "turn2"), []
    cut = payload.index(b"\n\n", len(payload) // 2) + 2

    class Slow(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            seen.append(1)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(payload[:cut])     # the usage chunk is in the part never sent
            self.wfile.flush()
            time.sleep(0.5)

        def log_message(self, *args):
            pass
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    try:
        with support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
            support.point_at(monkeypatch, "openai",
                             f"http://127.0.0.1:{upstream.server_address[1]}")
            target = urlparse(url)
            body = json.dumps({**MESSAGES, "stream": True, "messages": [
                {"role": "user", "content": prompt}]}).encode()
            sock = socket.create_connection((target.hostname, target.port), timeout=10)
            sock.sendall(_head("/v1/messages", raw, len(body)) + body)
            assert sock.recv(200).split(b" ", 2)[1] == b"200"
            time.sleep(0.1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, _LINGER_NOW)
            sock.close()                        # the client leaves before the usage chunk
            deadline = time.monotonic() + 8
            while not ledger.entries and time.monotonic() < deadline:
                time.sleep(0.02)
            entry = ledger.entries[0]
            assert entry.meta["reason"] in ("client_disconnected", "stream_incomplete")
            assert entry.kind == "endpoint_call_failed" and entry.meta["estimated"] is True
            assert entry.meta["charged_tokens"] >= least
            assert keys.row("ci-bot")["totals"]["tokens"] == entry.meta["charged_tokens"]
            # The key's limit of 1,000 is spent: the next call reaches no provider.
            assert post(url, "/v1/messages", raw)[0] == 400 and len(seen) == 1
    finally:
        upstream.shutdown()
        upstream.server_close()


def test_the_estimate_of_spaced_text_is_at_least_its_word_count_and_a_quarter_of_it():
    from harness import gateway_unaccounted, token_usage
    text = "one two three four five six seven eight nine ten " * 30
    words = token_usage.estimate(text, "")["prompt_words"]

    class Turn:
        caller = type("C", (), {"row": {}, "name": "k", "keys": type("K", (), {
            "debit": staticmethod(lambda name, counts, estimated: None)})()})()

        def text_form(self):
            return "", text
    began = type("A", (), {"began": True})()
    charged = gateway_unaccounted.partial_charge(Turn(), "client_disconnected", began, [])
    assert charged["estimated"] and charged["charged_tokens"] >= max(words, len(text) // 4)


# --- A2 -------------------------------------------------------------------------------

def test_a_request_paused_before_admission_cannot_be_admitted_on_a_stale_total(
        keyed, served, monkeypatch):
    """B has read its key's row and stalls before it takes a slot. A must not be
    able to run whole and be charged in that pause. Limit 400; each request asks
    for up to 400 output tokens, so one call in flight reserves the whole limit.

    Before the fix A ran to its end inside B's pause and B was then admitted on
    the total it had read: two calls served. Now A waits for B's admission and
    is refused, because B's reservation is held. (With a smaller reservation
    both would run together, which is the documented margin for calls in
    flight, not a stale total.)"""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=400)
    url, upstream, _ledger = served(turn2(2))
    ask = {**MESSAGES, "max_tokens": 400}
    real, stalled, go = gateway_key_policy.capped, threading.Event(), threading.Event()

    def capped(caller, path, body):
        if not stalled.is_set():
            stalled.set()                       # request B: its row is read, admission is next
            go.wait(1.5)
        return real(caller, path, body)
    monkeypatch.setattr(gateway_key_policy, "capped", capped)
    result = {}
    b = threading.Thread(target=lambda: result.update(b=post(url, "/v1/messages", raw, ask)[0]))
    b.start()
    assert stalled.wait(5)
    a = threading.Thread(target=lambda: result.update(a=post(url, "/v1/messages", raw, ask)[0]))
    a.start()
    a.join(0.7)
    finished_in_the_pause = not a.is_alive()
    go.set()
    a.join(20)
    b.join(20)
    assert not finished_in_the_pause, "A was admitted and served while B held a stale row"
    assert result == {"b": 200, "a": 429}       # A met B's reservation, not a stale total
    assert len(upstream.requests) == 1
    assert keys.row("ci-bot")["totals"]["tokens"] == TURN2_TOKENS


def test_control_calls_on_two_keys_and_calls_in_flight_still_run(keyed, served):
    keys, _store = keyed
    one, _ = keys.create("one")
    two, _ = keys.create("two")
    url, upstream, _ledger = served(turn2(6))
    statuses = []
    threads = [threading.Thread(target=lambda key=key: statuses.append(
        post(url, "/v1/messages", key)[0])) for key in (one, two, one, two, one, two)]
    [thread.start() for thread in threads]
    [thread.join(30) for thread in threads]
    assert statuses.count(200) == 6 and len(upstream.requests) == 6
    deadline = time.monotonic() + 5             # a slot is freed after its reply has left
    while gateway_key_policy._RUNNING and time.monotonic() < deadline:
        time.sleep(0.02)
    assert gateway_key_policy._RUNNING == {}    # every slot was freed


# --- N3 -------------------------------------------------------------------------------

@pytest.mark.parametrize("credential", [False, True])
def test_a_client_that_drips_header_lines_is_closed_at_the_head_deadline(
        keyed, served, monkeypatch, credential):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    monkeypatch.setenv(gateway_read_timeout.ENV, "0.5")
    url, upstream, _ledger = served(turn2(1))
    target, started, closed_at = urlparse(url), time.monotonic(), None
    with socket.create_connection((target.hostname, target.port), timeout=10) as sock:
        sock.sendall(b"POST /v1/messages HTTP/1.1\r\n"
                     + (f"x-api-key: {raw}\r\n".encode() if credential else b""))
        for index in range(20):                 # a line every 0.2 s: no single read times out
            try:
                sock.sendall(f"X-Pad-{index}: a\r\n".encode())
                sock.settimeout(0.2)
                if sock.recv(10) == b"":
                    closed_at = time.monotonic() - started
                    break
            except socket.timeout:
                continue
            except OSError:
                closed_at = time.monotonic() - started
                break
    assert closed_at is not None and closed_at < 2.0, closed_at
    assert upstream.requests == []


def test_a_body_that_keeps_dripping_is_answered_408_at_the_body_deadline(
        keyed, served, monkeypatch):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    monkeypatch.setenv(gateway_read_timeout.ENV, "0.5")     # the body gets 4 x 0.5 s
    url, upstream, ledger = served(turn2(1))
    target, started = urlparse(url), time.monotonic()
    with socket.create_connection((target.hostname, target.port), timeout=15) as sock:
        sock.sendall(_head("/v1/messages", raw, 5000))

        def drip():
            for _ in range(60):                 # a byte every 0.2 s, for up to 12 s
                try:
                    sock.sendall(b" ")
                except OSError:
                    return
                time.sleep(0.2)
        threading.Thread(target=drip, daemon=True).start()
        assert _status(sock) == 408
    assert 1.5 < time.monotonic() - started < 6
    assert upstream.requests == [] and ledger.entries == []


def test_control_keep_alive_requests_and_a_body_sent_in_pieces_are_served(
        keyed, served, monkeypatch):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    monkeypatch.setenv(gateway_read_timeout.ENV, "1.0")
    url, upstream, _ledger = served(turn2(3))
    target, payload = urlparse(url), json.dumps(MESSAGES).encode()
    with socket.create_connection((target.hostname, target.port), timeout=10) as sock:
        head = _head("/v1/messages", raw, len(payload))
        sock.sendall(head[:9])                  # the request line arrives in two pieces
        time.sleep(0.1)
        sock.sendall(head[9:] + payload[:10])
        time.sleep(0.3)
        sock.sendall(payload[10:])
        assert _status(sock) == 200
    assert [post(url, "/v1/messages", raw)[0] for _ in range(2)] == [200, 200]
    assert len(upstream.requests) == 3


def test_the_head_deadline_reader_reads_lines_as_the_plain_reader_does():
    import io
    data = b"POST / HTTP/1.1\r\nA: 1\r\nB: " + b"x" * 300 + b"\r\n\r\nbody-bytes"
    plain, wrapped = io.BufferedReader(io.BytesIO(data), 64), gateway_read_timeout.HeaderDeadline(
        io.BufferedReader(io.BytesIO(data), 64), 5.0)
    for size in (65537, 65537, 100, 65537, 65537):
        assert wrapped.readline(size) == plain.readline(size)
    assert wrapped.read(4) == plain.read(4) == b"body"
    late = gateway_read_timeout.HeaderDeadline(io.BufferedReader(io.BytesIO(data)), -1.0)
    with pytest.raises(TimeoutError):
        late.readline(65537)


# --- N5 -------------------------------------------------------------------------------

def test_show_cuts_a_long_field_and_full_prints_it_whole(tmp_path, capsys):
    ledger = gateway_ledger.GatewayLedger(tmp_path)
    long = "m" * 5000
    ledger.append("endpoint_call", "sha", {"key": "ci-bot", "model_ref": long,
                                           "reason": "r" * 81, "response_sha": "a" * 64})
    ledger.close()
    environ = {"FLYWHEEL_HOME": str(tmp_path)}
    assert gateway_ledger_cli.main(["show"], environ=environ) == 0
    out = capsys.readouterr().out
    assert len(out) < 600 and long not in out
    assert "m" * 80 + "...(+4920 more; --full shows all)" in out
    assert "response_sha=" + "a" * 64 in out                # a hash is printed whole
    assert gateway_ledger_cli.main(["show", "--full"], environ=environ) == 0
    assert long in capsys.readouterr().out
    assert gateway_ledger_cli.main(["show", "--json"], environ=environ) == 0
    assert json.loads(capsys.readouterr().out)["meta"]["model_ref"] == long
