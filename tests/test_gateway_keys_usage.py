"""The usage rule on every served endpoint, and a key's charge for an unreported count.

The rule: `usage` never carries an estimate; `x_flywheel.usage_reported` is on
every reply and in the ledger entry; a virtual key is charged the whitespace
word estimate when the provider sent no counts, and the charge is marked.

upstream/openai_no_usage is a reply with no `usage` block. The request is the
two words "What changed?" and the reply is the five words "Wrote n.txt.\\nNothing
else changed.", so the estimate is 2 + 5 = 7.
"""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from harness import gateway, gateway_keys, serve, token_usage
from harness.proposer import ProposerOutput
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, keyed, no_usage, post, served, stream_bytes, turn2)

PATHS = ["/v1/messages", "/v1/responses"]


@pytest.mark.parametrize("path", PATHS)
def test_an_unreported_count_is_charged_the_estimate_and_marked(keyed, served, path):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", price_in=1.0, price_out=1.0)
    url, _upstream, ledger = served(no_usage(1))
    status, _headers, body = post(url, path, raw)
    assert status == 200 and body["x_flywheel"] == {"usage_reported": False}
    row = keys.row("ci-bot")
    assert row["totals"] == {
        "calls": 1, "tokens": 7, "input_tokens": 2, "output_tokens": 5, "cache_read_tokens": 0,
        "cache_write_tokens": 0, "estimated_calls": 1, "estimated_tokens": 7}
    assert gateway_keys.spend(row) == 0.000007      # the estimate is priced the same way
    meta = ledger.entries[0].meta
    assert (meta["usage_reported"], meta["estimated"], meta["charged_tokens"]) == (False, True, 7)


@pytest.mark.parametrize("path, refused", [("/v1/messages", 400), ("/v1/responses", 429)])
def test_an_unreported_count_is_not_free_against_a_token_limit(keyed, served, path, refused):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=7)
    url, upstream, _ledger = served(no_usage(2))
    assert post(url, path, raw)[0] == 200
    assert post(url, path, raw)[0] == refused and len(upstream.requests) == 1


@pytest.mark.parametrize("path", PATHS)
def test_a_reported_count_is_flagged_true_and_not_marked_estimated(keyed, served, path):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served(turn2(1))
    _status, _headers, body = post(url, path, raw)
    assert body["x_flywheel"]["usage_reported"] is True
    meta = ledger.entries[0].meta
    assert meta["usage_reported"] is True and "estimated" not in meta
    assert keys.row("ci-bot")["totals"]["estimated_calls"] == 0


def test_messages_sends_zeros_and_responses_sends_null_for_an_unreported_count(served):
    url, _upstream, ledger = served(no_usage(2))
    _status, _headers, message = post(url, "/v1/messages", support.TOKEN)
    _status, _headers, response = post(url, "/v1/responses", support.TOKEN)
    assert message["usage"] == {"input_tokens": 0, "output_tokens": 0,
                                "cache_creation_input_tokens": None,
                                "cache_read_input_tokens": None}
    assert "usage" in response and response["usage"] is None
    assert message["x_flywheel"] == response["x_flywheel"] == {"usage_reported": False}
    metas = [entry.meta for entry in ledger.entries]
    assert [meta["usage_reported"] for meta in metas] == [False, False]
    assert all(meta["key"] == "owner" and "estimated" not in meta for meta in metas)


@pytest.mark.parametrize("path, event", [("/v1/messages", "message_delta"),
                                         ("/v1/responses", "response.completed")])
def test_a_stream_carries_the_flag_on_the_event_that_carries_usage(served, path, event):
    url, _upstream, _ledger = served([support.stream_answer(stream_bytes("openai", "turn2"))])
    _status, _headers, raw = post(url, path, support.TOKEN, {**BODIES[path], "stream": True})
    data = dict(support.events(raw))[event]
    carrier = data if path == "/v1/messages" else data["response"]
    assert carrier["x_flywheel"]["usage_reported"] is True
    assert isinstance(carrier["usage"], dict)


class _Proposer:
    model_ref = "stub"

    def __init__(self, usage):
        self.usage = usage

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput("alpha beta", self.model_ref, seed, "h", "stub", usage=self.usage)


@pytest.mark.parametrize("kept, reported", [
    ({"prompt_tokens": 1200, "completion_tokens": 34}, True), (None, False)])
def test_the_gateway_chat_completion_sets_the_flag_beside_slice_ones_fields(
        monkeypatch, kept, reported):
    monkeypatch.setattr(gateway, "_resolve_proposer",
                        lambda model, url: (_Proposer(kept), None, 200))
    body, code, *_ = gateway.openai_chat(
        {"model": "flywheel", "messages": [{"role": "user", "content": "one two three"}]},
        "http://x")
    assert code == 200 and body["x_flywheel"] == {"usage_reported": reported}
    assert (body["usage"] is not None) is reported      # slice 1's field is unchanged
    assert body["x_usage_estimate"]["prompt_words"] == 3


def _served_chat(monkeypatch, payload: dict) -> dict:
    """POST /chat/completions on the model server's own handler, with a stub model."""
    monkeypatch.setattr(serve, "generate", lambda *args: dict(payload))
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve._H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/chat/completions", method="POST",
            data=json.dumps({"messages": [{"role": "user", "content": "one two three"}]}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()


def test_the_model_servers_chat_completion_sends_null_usage_and_the_named_estimate(monkeypatch):
    """In 1.x this body carried `"usage": {}`, which reads as a count of nothing."""
    body = _served_chat(monkeypatch, {"text": "alpha beta", "seed": 0, "model_ref": "stub",
                                      "prompt_hash": "abc0000000000000", "cache": "miss"})
    assert "usage" in body and body["usage"] is None
    assert body["x_usage_estimate"]["method"] == "whitespace_words"
    assert body["x_usage_estimate"]["completion_words"] == 2
    assert body["x_usage_estimate"]["prompt_words"] >= 3
    assert body["x_flywheel"] == {"usage_reported": False}
    assert body["choices"][0]["message"]["content"] == "alpha beta" and "x_receipt" in body


def test_the_model_servers_chat_completion_passes_a_count_the_model_reported(monkeypatch):
    body = _served_chat(monkeypatch, {
        "text": "alpha beta", "seed": 0, "model_ref": "stub", "prompt_hash": "abc0000000000000",
        "cache": "miss", "token_usage": {"input_tokens": 11, "output_tokens": 4}})
    assert body["usage"] == {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}
    assert body["x_flywheel"] == {"usage_reported": True}


def test_chat_usage_never_puts_the_estimate_in_usage():
    fields = token_usage.chat_usage({"text": "a b c"}, "one two")
    assert fields == {"usage": None, "x_flywheel": {"usage_reported": False},
                      "x_usage_estimate": {"method": "whitespace_words", "prompt_words": 2,
                                           "completion_words": 3}}
