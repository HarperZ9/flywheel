"""A key's row is read and its slot taken as one step.

Independent review of 2.0.0, finding A2. The row was read again after the
request body, and the slot was taken afterwards under another lock. A request
paused between the two was admitted on a total that another call had changed
in the pause, so a key went past its limit by a whole call.

`gateway_key_gate.enter` now holds `gateway_key_policy.ADMISSION` from the
read to the admission, and a call that ends frees its slot under the same
lock. Two orders are tested, each with the pause forced by a hook on the
step between the read and the admission:

  a call that starts in the pause   it waits for the paused request's
                                    admission and then meets its reservation
  a call that ends in the pause     its slot stays held until the paused
                                    request has been admitted or refused

The key's limit is 400 tokens and each request asks for up to 400 output
tokens, so one call in flight reserves the whole limit and the right answer
to the second request is 429. With a smaller reservation two calls would run
together; that is the documented margin for calls in flight and is not what
these tests are about.

A real gateway on a loopback port with a stub upstream. No provider is called.
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness import gateway_key_policy
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    MESSAGES, TURN2_TOKENS, keyed, plain_object, post, served, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

ASK = {**MESSAGES, "max_tokens": 400}


def _stall_the_next_admission(monkeypatch, skip: int = 0):
    """(stalled, go): the request after `skip` others waits between its row read and its slot."""
    real, stalled, go, seen = gateway_key_policy.capped, threading.Event(), threading.Event(), []

    def capped(caller, path, body):
        seen.append(1)
        if len(seen) == skip + 1:
            stalled.set()                       # its row is read; admission is next
            go.wait(3.0)
        return real(caller, path, body)
    monkeypatch.setattr(gateway_key_policy, "capped", capped)
    return stalled, go


def test_a_call_that_starts_in_the_pause_waits_and_meets_the_reservation(
        keyed, served, monkeypatch):
    """Before the fix A ran to its end inside B's pause and B was then admitted on
    the total it had read: two calls served, 920 tokens against a limit of 400."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=400)
    url, upstream, _ledger = served(turn2(2))
    stalled, go = _stall_the_next_admission(monkeypatch)
    result = {}
    b = threading.Thread(target=lambda: result.update(b=post(url, "/v1/messages", raw, ASK)[0]))
    b.start()
    assert stalled.wait(5)
    a = threading.Thread(target=lambda: result.update(a=post(url, "/v1/messages", raw, ASK)[0]))
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


def test_a_call_that_ends_in_the_pause_keeps_its_slot_until_the_admission(
        keyed, monkeypatch, tmp_path):
    """C is in flight when B reads the row. C ends, and is charged, while B is paused.
    B must still see C: as a reservation, because C's slot is freed under the lock
    B holds. With two locks B saw no reservation and an old total, and was served."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=400)
    reached, reply = threading.Event(), json.dumps(plain_object("openai", "turn2")).encode()
    calls = []

    class Slow(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            calls.append(self.path)
            reached.set()
            time.sleep(0.6)                     # C is in flight for this long
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    try:
        with support.gateway_server(monkeypatch, tmp_path) as (url, _ledger):
            support.point_at(monkeypatch, "openai",
                             f"http://127.0.0.1:{upstream.server_address[1]}")
            stalled, go = _stall_the_next_admission(monkeypatch, skip=1)
            result = {}
            c = threading.Thread(
                target=lambda: result.update(c=post(url, "/v1/messages", raw, ASK)[0]))
            c.start()
            assert reached.wait(5)              # C holds its slot and is at the provider
            b = threading.Thread(
                target=lambda: result.update(b=post(url, "/v1/messages", raw, ASK)[0]))
            b.start()
            assert stalled.wait(5)              # B has read the row: C is not charged yet
            c.join(10)                          # C's reply has reached its client
            assert result.get("c") == 200
            assert keys.row("ci-bot")["totals"]["tokens"] == TURN2_TOKENS   # and C is charged
            go.set()
            b.join(20)
            assert result["b"] == 429, "B was admitted on the total it read before C was charged"
            assert len(calls) == 1
            assert keys.row("ci-bot")["totals"]["tokens"] == TURN2_TOKENS
    finally:
        upstream.shutdown()
        upstream.server_close()


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
