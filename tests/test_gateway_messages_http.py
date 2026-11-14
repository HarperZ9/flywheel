"""The Messages interface over HTTP: a real gateway, a loopback stub upstream.

The gateway runs on a loopback port chosen by the system and talks to a stub
provider over real sockets. The equivalence test at the end sends one
conversation through the OpenAI-chat path and through Messages and compares
the two ledger entries.

Wire formats, read 2026-11-13:
  https://platform.claude.com/docs/en/api/messages/create
  https://platform.claude.com/docs/en/build-with-claude/streaming
  https://platform.claude.com/docs/en/api/errors
  https://code.claude.com/docs/en/llm-gateway-connect.md (ANTHROPIC_AUTH_TOKEN is
      sent as Authorization: Bearer, ANTHROPIC_API_KEY as x-api-key)
"""
import json
import urllib.error
import urllib.request
from dataclasses import replace

import pytest

from harness import gateway, gateway_turn, providers
from harness.local_session import SessionLedger
from tests import gateway_messages_support as support
from tests.hosted_stream_fixtures import plain_object, stream_bytes

API_KEY = {"x-api-key": support.TOKEN}


def _post(url, path, body, headers):
    request = urllib.request.Request(
        url + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


@pytest.mark.parametrize("headers", [API_KEY, {"Authorization": f"Bearer {support.TOKEN}"}])
def test_plain_request_over_http_with_either_credential_header(monkeypatch, tmp_path, headers):
    with support.Upstream([support.json_answer(plain_object("openai", "turn2"))]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "openai", upstream.url)
        status, sent, raw = _post(url, "/v1/messages", support.load("requests/text.json"), headers)
    body = json.loads(raw)
    assert status == 200 and sent["Content-Type"] == "application/json"
    assert {k: v for k, v in body.items() if k not in ("id", "x_receipt")} == support.load(
        "expected/openai_text.json")
    assert sent["x-receipt-id"] == body["x_receipt"]["receipt_id"]
    assert upstream.requests[0]["path"] == "/v1/chat/completions"
    assert upstream.requests[0]["headers"]["authorization"] == "Bearer test-key"
    assert support.TOKEN not in json.dumps(upstream.requests)      # the gateway token stays here
    assert support.kinds(ledger) == ["endpoint_call"]


@pytest.mark.parametrize("headers, reason", [
    ({}, "no_token"), ({"x-api-key": "wrong"}, "bad_token"),
    ({"Authorization": "Bearer wrong", "x-api-key": support.TOKEN}, "bad_token")])
def test_wrong_or_missing_token_is_401_and_nothing_goes_upstream(monkeypatch, tmp_path, headers,
                                                                 reason):
    with support.Upstream([]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "openai", upstream.url)
        status, _sent, raw = _post(url, "/v1/messages", support.load("requests/text.json"), headers)
    assert status == 401 and json.loads(raw)["reason"] == reason
    assert upstream.requests == [] and ledger.entries == []


def test_malformed_request_over_http_reaches_no_upstream(monkeypatch, tmp_path):
    with support.Upstream([]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "openai", upstream.url)
        bad = {key: value for key, value in support.load("requests/text.json").items()
               if key != "max_tokens"}
        status, _sent, raw = _post(url, "/v1/messages", bad, API_KEY)
        not_json = urllib.request.Request(
            url + "/v1/messages", data=b"{not json", method="POST",
            headers={"Content-Type": "application/json", **API_KEY})
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(not_json, timeout=30)
    body = json.loads(raw)
    assert status == 400 and body["type"] == "error"
    assert body["error"]["type"] == "invalid_request_error"
    assert refused.value.code == 400
    assert json.loads(refused.value.read())["error"]["type"] == "invalid_request_error"
    assert upstream.requests == []            # the stub saw zero requests
    assert ledger.entries == []               # and no endpoint_call entry was written


def test_streamed_text_over_http(monkeypatch, tmp_path):
    with support.Upstream([support.stream_answer(stream_bytes("openai", "turn2"))]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "openai", upstream.url)
        status, sent, raw = _post(url, "/v1/messages", support.load("requests/stream_text.json"),
                                  API_KEY)
    got = support.events(raw)
    want = support.load("expected/openai_stream_text.events.json")
    got[0][1]["message"].pop("id")
    want[0][1]["message"].pop("id")
    got[-1][1].pop("x_receipt")
    assert status == 200 and sent["Content-Type"] == "text/event-stream"
    assert got == want
    assert upstream.requests[0]["body"]["stream"] is True
    assert support.kinds(ledger) == ["endpoint_call"]


def test_anthropic_stream_cut_mid_event_over_http(monkeypatch, tmp_path):
    cut = support.raw("upstream/anthropic_cut.sse")
    with support.Upstream([support.stream_answer(cut)]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "anthropic", upstream.url)
        status, _sent, raw = _post(url, "/v1/messages", support.load("requests/stream_text.json"),
                                   {**API_KEY, "anthropic-version": "2023-06-01"})
    got = support.events(raw)
    assert status == 200                      # the stream had begun when it broke
    assert got[-1][0] == "error" and got[-1][1]["error"]["type"] == "api_error"
    assert "message_stop" not in [name for name, _ in got]
    assert upstream.requests[0]["path"] == "/v1/messages"
    assert upstream.requests[0]["headers"]["x-api-key"] == "test-key"
    assert support.kinds(ledger) == ["endpoint_call_failed"]


def test_anthropic_error_keeps_its_body_status_and_retry_headers(monkeypatch, tmp_path):
    sent = support.load("upstream/anthropic_overloaded.json")
    refusal = (*support.json_answer(sent, 529), {"retry-after": "7", "x-should-retry": "true"})
    with support.Upstream([refusal]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "anthropic", upstream.url)
        status, headers, raw = _post(url, "/v1/messages", support.load("requests/text.json"),
                                     API_KEY)
    assert (status, json.loads(raw)) == (529, sent)
    assert (headers["retry-after"], headers["x-should-retry"]) == ("7", "true")
    assert support.kinds(ledger) == ["endpoint_call_failed"]
    assert ledger.entries[0].meta["reason"] == "upstream_status_529"


def test_count_tokens_over_http(monkeypatch, tmp_path):
    with support.Upstream([support.json_answer({"input_tokens": 14})]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "anthropic", upstream.url)
        status, _sent, raw = _post(url, "/v1/messages/count_tokens",
                                   support.load("requests/text.json"), API_KEY)
        support.point_at(monkeypatch, "openai", upstream.url)
        missing, _sent, other = _post(url, "/v1/messages/count_tokens",
                                      support.load("requests/text.json"), API_KEY)
    assert (status, json.loads(raw)) == (200, {"input_tokens": 14})
    assert upstream.requests[0]["path"] == "/v1/messages/count_tokens"
    assert missing == 404 and json.loads(other)["error"]["type"] == "not_found_error"
    assert len(upstream.requests) == 1 and ledger.entries == []


def _chat_and_messages(monkeypatch, record=None):
    """One text conversation through both interfaces; the two ledger entries."""
    reply = plain_object("openai", "turn2")
    reply["choices"][0]["message"]["content"] = "Nothing else changed.\n"
    ledger = SessionLedger()
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", ledger)
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [{"name": "ollama", "credential": "local-none"}], "usable_names": ["ollama"]})
    if record is not None:
        monkeypatch.setattr(gateway_turn, "record", record)
    with support.Upstream([support.json_answer(reply)] * 2) as upstream:
        monkeypatch.setitem(providers.REGISTRY, "ollama", replace(
            providers.REGISTRY["ollama"], base_url=f"{upstream.url}/v1"))
        chat = {"model": "ollama:stub-model", "messages": [
            {"role": "system", "content": "Be brief."}, {"role": "user", "content": "What changed?"}]}
        body, code, *_rest = gateway.openai_chat(chat, "http://127.0.0.1:9")
        from harness import gateway_messages
        answer = gateway_messages.handle(
            {"model": "ollama:stub-model", "max_tokens": 512, "system": "Be brief.",
             "messages": [{"role": "user", "content": "What changed?"}]}, {}, ledger, environ={})
        assert code == 200 and answer.status == 200 and len(upstream.requests) == 2
    assert body["choices"][0]["message"]["content"] == answer.body["content"][0]["text"]
    return ledger.entries


def _equivalent(chat, messages) -> None:
    """Design point 5: the same call on either interface leaves the same entry."""
    assert chat.kind == messages.kind == "endpoint_call"
    assert chat.content == messages.content
    assert messages.meta.get("interface") == "anthropic-messages"
    assert chat.meta == {key: value for key, value in messages.meta.items() if key != "interface"}


def test_chat_and_messages_leave_equal_ledger_entries(monkeypatch):
    chat, messages = _chat_and_messages(monkeypatch)
    _equivalent(chat, messages)
    assert set(chat.meta) == {"endpoint", "model_ref", "seed", "prompt_sha", "response_sha"}
    assert chat.meta["model_ref"] == "ollama:stub-model"


@pytest.mark.parametrize("lost", ["model_ref", "prompt_sha", "endpoint"])
def test_equivalence_fails_when_one_path_drops_a_meta_key(monkeypatch, lost):
    whole = gateway_turn.record

    class Dropping:
        def __init__(self, ledger):
            self.ledger = ledger

        def append(self, kind, content, meta):
            self.ledger.append(kind, content, {k: v for k, v in meta.items() if k != lost})

    def record(ledger, upstream, turn, reply):
        whole(Dropping(ledger), upstream, turn, reply)

    chat, messages = _chat_and_messages(monkeypatch, record)
    with pytest.raises(AssertionError):
        _equivalent(chat, messages)
