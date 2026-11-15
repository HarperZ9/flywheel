"""The one unbilled contact, and the contacts of the routes outside the model interfaces.

Fifth review round of 2.0.0, the lead's rulings 5 and 6.

Token counting (ruling 6). `/v1/messages/count_tokens` is the one request the
gateway sends to a provider with no ledger entry. It stays that way only
because it cannot reach anything that bills:

  Anthropic upstream   forwarded to `<base>/v1/messages/count_tokens`, which the
                       Claude API documents as free to use, with its own
                       request-per-minute limits. It creates no message.
                       https://platform.claude.com/docs/en/build-with-claude/token-counting
                       ("Pricing and rate limits"), read 2026-11-14.
  OpenAI format        answered 404 by the gateway; nothing is sent.
  Gemini               answered 404 by the gateway; nothing is sent.

and `gateway_account.unbilled` refuses any URL that is not a token-count URL,
so the unbilled path cannot be pointed at a route that runs a model. Not
verified: a live call to the Claude API; the claim about its price is the
documentation's.

Contacts (ruling 5). tests/test_gateway_contact_invariant.py watches the
transport of /v1/messages and /v1/responses. The chat routes and
/v1/embeddings reach their provider through `urllib.request.urlopen`, so this
file watches that: each contact is made inside a `gateway_account.Call`.

A stub upstream on a loopback port, or a fake `urlopen`. No provider is called.
"""
import urllib.request
from dataclasses import replace

import pytest

from harness import gateway, gateway_account, providers
from harness.local_session import SessionLedger
from tests import gateway_messages_support as support
from tests.gateway_keys_support import BODIES, keyed, post, served, turn2  # noqa: F401

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_token_counting_reaches_no_upstream_that_is_not_anthropic(served, provider):
    url, upstream, ledger = served([support.json_answer({"input_tokens": 12})], provider)
    status, _headers, body = post(url, "/v1/messages/count_tokens", support.TOKEN,
                                  BODIES["/v1/messages"])
    assert status == 404 and body["error"]["type"] == "not_found_error"
    assert "no estimate is returned" in body["error"]["message"]
    assert upstream.requests == [] and ledger.entries == []


def test_token_counting_on_an_anthropic_upstream_goes_to_the_count_route_only(served):
    url, upstream, ledger = served([support.json_answer({"input_tokens": 12})], "anthropic")
    status, _headers, body = post(url, "/v1/messages/count_tokens", support.TOKEN,
                                  BODIES["/v1/messages"])
    assert status == 200 and body == {"input_tokens": 12}
    assert [request["path"] for request in upstream.requests] == ["/v1/messages/count_tokens"]
    assert ledger.entries == []


@pytest.mark.parametrize("url", [
    "https://api.anthropic.com/v1/messages",
    "https://api.anthropic.com/v1/messages/count_tokens/../",
    "https://api.openai.com/v1/chat/completions",
    "https://api.anthropic.com/v1/messages?x=/v1/messages/count_tokens",
])
def test_the_unbilled_path_refuses_a_url_that_is_not_a_token_count(url):
    sent = []
    with pytest.raises(RuntimeError, match="token-count"):
        gateway_account.unbilled(lambda: sent.append(1), url)
    assert sent == [], "the request left before the URL was checked"


def test_control_the_unbilled_path_sends_a_token_count():
    assert gateway_account.unbilled(lambda: "sent",
                                    "https://api.anthropic.com/v1/messages/count_tokens") == "sent"


# --- The chat routes and embeddings contact their provider inside a Call --------------------

@pytest.fixture
def watched(monkeypatch):
    """Record `gateway_account.contacting()` at every `urllib.request.urlopen`."""
    seen, real = [], urllib.request.urlopen

    def urlopen(*args, **kwargs):
        who = gateway_account.contacting()
        seen.append((type(who).__name__, getattr(who, "state", None)))
        return real(*args, **kwargs)
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return seen


def test_every_contact_of_the_chat_and_embeddings_routes_is_made_inside_a_call(
        monkeypatch, watched):
    ledger = SessionLedger()
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", ledger)
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [{"name": "ollama", "credential": "local-none"}], "usable_names": ["ollama"]})
    embedding = support.json_answer({"data": [{"embedding": [0.5]}]})
    with support.Upstream([*turn2(2), embedding]) as upstream:
        base = f"{upstream.url}/v1"
        monkeypatch.setitem(providers.REGISTRY, "ollama", replace(
            providers.REGISTRY["ollama"], base_url=base))
        monkeypatch.setitem(providers.REGISTRY, "xprov", type("Spec", (), {
            "base_url": base, "api_key_env": "", "local": False, "default_model": "e"})())
        chat = {"model": "ollama:stub-model", "messages": [{"role": "user", "content": "Hi."}]}
        assert gateway.openai_chat(chat, "http://127.0.0.1:9")[1] == 200
        assert gateway.route_request("Hi.", "ollama", "stub-model")[1] == 200
        assert gateway.openai_embeddings({"model": "xprov:embed-3", "input": "hi"})[1] == 200
        assert len(upstream.requests) == 3
    assert watched == [("Call", "contacted")] * 3
    assert support.kinds(ledger) == ["endpoint_call"] * 3


def test_control_a_contact_outside_a_call_is_seen_by_the_watch(watched):
    with support.Upstream([support.json_answer({})]) as upstream:
        urllib.request.urlopen(urllib.request.Request(
            upstream.url + "/v1/x", data=b"{}", method="POST"), timeout=10).close()
    assert watched == [("NoneType", None)]
