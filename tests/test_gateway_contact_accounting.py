"""No upstream contact without accounting: review 3, finding R1, and its family.

R1. A request whose text cannot be encoded as UTF-8 (a lone surrogate, sent as
the JSON escape `\\ud800`) reached the provider, and the gateway then failed
while it built the ledger entry. A streamed reply was delivered whole with no
entry, no charge and no suspension.

Two rules are tested here.

  before contact   a request the gateway cannot hash is refused with 400 and
                   nothing is sent upstream;
  after contact    whatever fails, the call leaves exactly one ledger entry,
                   and a key is charged or suspended.

The second rule is tested by fault injection in
tests/test_gateway_contact_invariant.py.

A real gateway on a loopback port, a stub upstream replaying recorded replies,
keys in the in-memory store. No provider is called.
"""
import json

import pytest

from tests import gateway_messages_support as support
from tests.gateway_contact_support import (
    ESCAPE, PATHS, PROVIDERS, calls, raw_post, unhashable)
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, keyed, plain_object, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


# --- R1 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("path", PATHS)
def test_r1_a_streamed_request_that_cannot_be_hashed_is_not_served_for_free(
        keyed, served, path, provider):
    """The reviewer's probe: eight streamed calls against a limit one call uses up."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=500)        # one turn2 call costs 460
    answers = [support.stream_answer(stream_bytes(provider, "turn2"))] * 8
    url, upstream, ledger = served(answers, provider)
    served_text = 0
    for _ in range(8):
        status, body = raw_post(url, path, raw, unhashable(path, True))
        served_text += status == 200 and (b"text_delta" in body or b"output_text.delta" in body)
    assert len(calls(ledger)) == len(upstream.requests), (
        f"{len(upstream.requests)} upstream call(s) and {len(calls(ledger))} ledger entries")
    assert served_text <= 1, f"{served_text} of 8 replies were delivered against the limit"
    assert len(upstream.requests) == 0, "the request is refused before any upstream call"
    assert keys.row("ci-bot")["totals"]["tokens"] == 0


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("path", PATHS)
def test_r1_the_refusal_is_a_400_that_names_the_reason_and_sends_nothing(
        keyed, served, path, stream):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=500)
    url, upstream, ledger = served(turn2(1))
    status, body = raw_post(url, path, raw, unhashable(path, stream))
    assert status == 400
    assert b"UTF-8" in body and b"Nothing was sent upstream" in body
    assert upstream.requests == [] and keys.row("ci-bot")["totals"]["tokens"] == 0
    assert [e.kind for e in support.recorded(ledger)] == []
    status, _headers, _body = post(url, path, raw)          # control: the same call, hashable
    assert status == 200 and len(upstream.requests) == 1
    assert support.kinds(ledger) == ["endpoint_call"]


# --- Each layer alone ----------------------------------------------------------------------
#
# The HTTP route refuses at intake, and `Account` refuses again at the point of contact.
# These tests reach one layer each, so that removing either one fails a test.

@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("stream", [False, True])
def test_the_account_refuses_an_unhashable_turn_with_no_intake_check_in_the_way(
        monkeypatch, provider, stream):
    """`handle` called directly: no HTTP route, so only `Account` stands before the upstream."""
    from harness import gateway_messages, gateway_responses
    from harness.local_session import SessionLedger
    lone = chr(0xD800)
    made = support.replayed(monkeypatch, provider,
                            plain=[plain_object(provider, "turn2")] * 2,
                            streams=[stream_bytes(provider, "turn2")] * 2)
    ledger = SessionLedger()
    answer = gateway_messages.handle(
        {"model": "claude-sonnet-5", "max_tokens": 64, "stream": stream,
         "messages": [{"role": "user", "content": "hi " + lone}]}, {}, ledger)
    other = gateway_responses.handle(
        {"model": "gpt-5.3-codex", "input": "hi " + lone, "stream": stream}, {}, ledger)
    assert (answer.status, other.status) == (400, 400)
    assert "UTF-8" in answer.body["error"]["message"]
    assert "UTF-8" in other.body["error"]["message"]
    assert ledger.entries == []
    assert made.transport.requests == [] and made.stream_transport.requests == []


@pytest.mark.parametrize("path", PATHS)
def test_the_intake_check_refuses_a_lone_surrogate_in_a_field_the_ledger_does_not_hash(
        keyed, served, path):
    """A surrogate in a tool description: outside the prompt hash, refused at intake."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger = served(turn2(1))
    tool = ({"name": "look", "description": "DESC", "input_schema": {"type": "object"}}
            if path == "/v1/messages" else
            {"type": "function", "name": "look", "description": "DESC",
             "parameters": {"type": "object"}})
    body = json.dumps({**BODIES[path], "tools": [tool]}).replace('"DESC"', '"' + ESCAPE + '"')
    status, answer = raw_post(url, path, raw, body.encode())
    assert status == 400 and b"UTF-8" in answer
    assert upstream.requests == [] and ledger.entries == []


def test_a_reply_the_gateway_cannot_hash_is_refused_and_recorded(keyed, served):
    """The same fault from the other side: the upstream's reply holds a lone surrogate."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    reply = plain_object("openai", "turn2")
    reply["choices"][0]["message"]["content"] = "Nothing else changed. MARK"
    bad = json.dumps(reply).replace("MARK", ESCAPE).encode()
    url, upstream, ledger = served([(200, "application/json", bad)])
    status, _headers, body = post(url, "/v1/messages", raw)
    assert status == 502 and "UTF-8" in body["error"]["message"]
    entry, = support.recorded(ledger)
    assert (entry.kind, entry.meta["reason"]) == ("endpoint_call_failed", "malformed_reply")
    assert len(upstream.requests) == 1


# --- The owner's chat routes (/v1/chat/completions, /api/route) ----------------------------
#
# These routes take the gateway token only, so no key budget is at stake. They had the
# same fault: the prompt was hashed after the provider had answered.

def _chat_route(monkeypatch, replies):
    """(upstream, ledger) with the `ollama` endpoint pointed at a loopback stub."""
    from dataclasses import replace
    from harness import gateway, providers
    from harness.local_session import SessionLedger
    ledger = SessionLedger()
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", ledger)
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [{"name": "ollama", "credential": "local-none"}], "usable_names": ["ollama"]})
    upstream = support.Upstream(replies).__enter__()
    monkeypatch.setitem(providers.REGISTRY, "ollama", replace(
        providers.REGISTRY["ollama"], base_url=f"{upstream.url}/v1"))
    return upstream, ledger


def test_the_chat_routes_send_nothing_for_a_prompt_they_cannot_hash(monkeypatch):
    from harness import gateway
    upstream, ledger = _chat_route(monkeypatch, turn2(3))
    try:
        lone = "What changed? " + chr(0xD800)
        body, code, *_rest = gateway.openai_chat(
            {"model": "ollama:stub-model", "messages": [{"role": "user", "content": lone}]},
            "http://127.0.0.1:9")
        assert code == 502 and upstream.requests == []
        answer, status = gateway.route_request(lone, "ollama", "stub-model")
        assert status == 502 and "nothing was sent upstream" in answer["error"]
        assert upstream.requests == [] and ledger.entries == []
        body, code, *_rest = gateway.openai_chat(             # control: a prompt that hashes
            {"model": "ollama:stub-model", "messages": [{"role": "user", "content": "Hi."}]},
            "http://127.0.0.1:9")
        assert code == 200 and len(upstream.requests) == 1
        assert support.kinds(ledger) == ["endpoint_call"]
    finally:
        upstream.__exit__(None, None, None)


def test_the_chat_route_records_a_reply_it_cannot_hash(monkeypatch):
    from harness import gateway
    reply = plain_object("openai", "turn2")
    reply["choices"][0]["message"]["content"] = "Nothing else changed. MARK"
    bad = json.dumps(reply).replace("MARK", ESCAPE).encode()
    upstream, ledger = _chat_route(monkeypatch, [(200, "application/json", bad)])
    try:
        _body, code, *_rest = gateway.openai_chat(
            {"model": "ollama:stub-model", "messages": [{"role": "user", "content": "Hi."}]},
            "http://127.0.0.1:9")
        assert code == 502 and len(upstream.requests) == 1
        entry, = support.recorded(ledger)
        assert (entry.kind, entry.content) == ("endpoint_call_failed", "malformed_reply")
        assert len(entry.meta["prompt_sha"]) == 16
    finally:
        upstream.__exit__(None, None, None)
