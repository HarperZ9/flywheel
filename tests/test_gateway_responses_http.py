"""The Responses interface over HTTP: a real gateway, a loopback stub upstream.

The gateway runs on a loopback port chosen by the system and talks to a stub
provider over real sockets. The equivalence tests at the end send one
conversation through the OpenAI-chat path, through Responses and through
Messages, and compare the ledger entries.

Wire format, read 2026-11-14. platform.openai.com refused the fetch (403), so:
  https://github.com/openai/openai-openapi (manual_spec branch, openapi.yaml):
      Response, the createResponse streaming example, ErrorResponse,
      ResponseFailedEvent
  openai Python SDK 2.36.0, types/responses (generated from that spec)
  https://developers.openai.com/api/docs/guides/function-calling
"""
import json
import urllib.error
import urllib.request
from dataclasses import replace

import pytest

from harness import gateway, gateway_messages, gateway_responses, gateway_turn, providers
from harness.local_session import SessionLedger
from tests import gateway_responses_support as support
from tests.hosted_stream_fixtures import NATIVE, plain_object, stream_bytes

BEARER = {"Authorization": f"Bearer {support.TOKEN}"}
TEXT = "Wrote n.txt.\nNothing else changed."


def _post(url, body, headers=BEARER, raw=None):
    request = urllib.request.Request(
        url + "/v1/responses", data=json.dumps(body).encode() if raw is None else raw,
        method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


@pytest.mark.parametrize("provider, path", [
    ("openai", "/v1/chat/completions"), ("anthropic", "/v1/messages"),
    ("gemini", "/v1beta/models/gemini-2.5-flash:generateContent")])
def test_plain_request_over_http_for_each_upstream_dialect(monkeypatch, tmp_path, provider, path):
    with support.Upstream([support.json_answer(plain_object(provider, "turn2"))]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, provider, upstream.url)
        status, sent, raw = _post(url, support.load("requests/text.json"))
    body = json.loads(raw)
    assert status == 200 and sent["Content-Type"] == "application/json"
    assert support.normal(body) == support.load(f"expected/{provider}_text.json")
    assert sent["x-receipt-id"] == body["x_receipt"]["receipt_id"]
    assert sent["x-request-id"].startswith("req_")
    assert upstream.requests[0]["path"].split("?")[0] == path     # never /v1/responses
    assert support.TOKEN not in json.dumps(upstream.requests)      # the gateway token stays here
    assert support.kinds(ledger) == ["endpoint_call"]


@pytest.mark.parametrize("headers, reason", [({}, "no_token"),
                                             ({"Authorization": "Bearer wrong"}, "bad_token")])
def test_wrong_or_missing_token_is_401_and_nothing_goes_upstream(monkeypatch, tmp_path, headers,
                                                                 reason):
    with support.Upstream([]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "openai", upstream.url)
        status, _sent, raw = _post(url, support.load("requests/text.json"), headers)
    assert status == 401 and json.loads(raw)["reason"] == reason
    assert upstream.requests == [] and ledger.entries == []


def test_malformed_request_over_http_reaches_no_upstream(monkeypatch, tmp_path):
    with support.Upstream([]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "openai", upstream.url)
        status, _sent, raw = _post(url, {"model": "gpt-5.3-codex"})
        broken, _sent, not_json = _post(url, None, raw=b"{not json")
        stored, _sent, refused = _post(url, {"model": "gpt-5.3-codex", "input": "hi",
                                             "previous_response_id": "resp_abc"})
    for code, answer in ((status, raw), (broken, not_json), (stored, refused)):
        error = json.loads(answer)["error"]
        assert code == 400 and error["type"] == "invalid_request_error"
        assert set(error) == {"message", "type", "param", "code"}
    assert json.loads(refused)["error"]["param"] == "previous_response_id"
    assert upstream.requests == []            # the stub saw zero requests
    assert ledger.entries == []               # and no endpoint_call entry was written


@pytest.mark.parametrize("request_name, recording, expected", [
    ("requests/stream_text.json", "turn2", "expected/openai_stream_text.events.json"),
    ("requests/stream_tools.json", "tool_call", "expected/openai_stream_tool.events.json")])
def test_streamed_text_and_function_call_over_http(monkeypatch, tmp_path, request_name,
                                                   recording, expected):
    answer = support.stream_answer(stream_bytes("openai", recording))
    with support.Upstream([answer]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "openai", upstream.url)
        status, sent, raw = _post(url, support.load(request_name))
    assert status == 200 and sent["Content-Type"] == "text/event-stream"
    assert support.normal(support.events(raw)) == support.load(expected)
    assert upstream.requests[0]["body"]["stream"] is True
    assert support.kinds(ledger) == ["endpoint_call"]


def test_stream_cut_mid_event_over_http(monkeypatch, tmp_path):
    cut = support.upstream_raw("upstream/openai_cut.sse")
    with support.Upstream([support.stream_answer(cut)]) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, "openai", upstream.url)
        status, _sent, raw = _post(url, support.load("requests/stream_text.json"))
    got = support.events(raw)
    names = [name for name, _data in got]
    assert status == 200                      # the stream had begun when it broke
    assert names[-1] == "response.failed" and "response.completed" not in names
    assert got[-1][1]["response"]["status"] == "failed"
    assert got[-1][1]["response"]["error"]["code"] == "server_error"
    assert len(upstream.requests) == 1
    assert support.kinds(ledger) == ["endpoint_call_failed"]


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
def test_tool_round_trip_over_http_for_each_upstream_dialect(monkeypatch, tmp_path, provider):
    answers = [support.json_answer(plain_object(provider, NATIVE[provider])),
               support.json_answer(plain_object(provider, "turn2"))]
    request = support.load("requests/tools.json")
    with support.Upstream(answers) as upstream, \
            support.gateway_server(monkeypatch, tmp_path) as (url, ledger):
        support.point_at(monkeypatch, provider, upstream.url)
        _status, _sent, raw = _post(url, request)
        first = json.loads(raw)
        call = next(item for item in first["output"] if item["type"] == "function_call")
        history = [{"role": "user", "content": request["input"]}, *first["output"],
                   {"type": "function_call_output", "call_id": call["call_id"],
                    "output": "wrote 2 bytes"}]
        status, _sent, raw = _post(url, {**request, "input": history, "tool_choice": "auto"})
    second = json.loads(raw)
    assert (call["name"], json.loads(call["arguments"])) == (
        "write_file", {"path": "n.txt", "content": "hi"})
    assert status == 200 and second["output"][0]["content"][0]["text"] == TEXT
    told = json.dumps(upstream.requests[1]["body"])
    assert "wrote 2 bytes" in told and "write_file" in told   # the call and its result went up
    assert support.kinds(ledger) == ["endpoint_call", "endpoint_call"] and ledger.verify()


def _three_ways(monkeypatch, record=None):
    """One text conversation through chat, Responses and Messages; the entries."""
    reply = plain_object("openai", "turn2")
    reply["choices"][0]["message"]["content"] = "Nothing else changed.\n"
    ledger = SessionLedger()
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", ledger)
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [{"name": "ollama", "credential": "local-none"}], "usable_names": ["ollama"]})
    if record is not None:
        monkeypatch.setattr(gateway_turn, "record", record)
    with support.Upstream([support.json_answer(reply)] * 3) as upstream:
        monkeypatch.setitem(providers.REGISTRY, "ollama", replace(
            providers.REGISTRY["ollama"], base_url=f"{upstream.url}/v1"))
        chat = {"model": "ollama:stub-model", "messages": [
            {"role": "system", "content": "Be brief."}, {"role": "user", "content": "What changed?"}]}
        body, code, *_rest = gateway.openai_chat(chat, "http://127.0.0.1:9")
        answer = gateway_responses.handle(
            {"model": "ollama:stub-model", "instructions": "Be brief.",
             "input": [{"role": "user", "content": "What changed?"}]}, {}, ledger, environ={})
        message = gateway_messages.handle(
            {"model": "ollama:stub-model", "max_tokens": 512, "system": "Be brief.",
             "messages": [{"role": "user", "content": "What changed?"}]}, {}, ledger, environ={})
        assert code == 200 and answer.status == 200 and message.status == 200
        assert len(upstream.requests) == 3
    said = body["choices"][0]["message"]["content"]
    assert said == answer.body["output"][0]["content"][0]["text"] == message.body["content"][0]["text"]
    return ledger.entries


def _equivalent(chat, other, interface: str) -> None:
    """Design point 5: the same call on either interface leaves the same entry."""
    assert chat.kind == other.kind == "endpoint_call"
    assert chat.content == other.content
    assert other.meta.get("interface") == interface
    assert other.meta.get("key") == "owner" and other.meta.get("usage_reported") is True
    assert chat.meta == {key: value for key, value in other.meta.items()
                         if key not in ("interface", "key", "usage_reported")}


def test_chat_responses_and_messages_leave_equal_ledger_entries(monkeypatch):
    chat, responses, messages = _three_ways(monkeypatch)
    _equivalent(chat, responses, "openai-responses")
    _equivalent(chat, messages, "anthropic-messages")
    assert set(chat.meta) == {"endpoint", "model_ref", "seed", "prompt_sha", "response_sha"}
    assert chat.meta["model_ref"] == "ollama:stub-model"


@pytest.mark.parametrize("lost", ["model_ref", "prompt_sha", "endpoint"])
def test_equivalence_fails_when_the_responses_path_drops_a_meta_key(monkeypatch, lost):
    whole = gateway_turn.record

    class Dropping:
        def __init__(self, ledger):
            self.ledger = ledger

        def append(self, kind, content, meta):
            self.ledger.append(kind, content, {k: v for k, v in meta.items() if k != lost})

    def record(ledger, upstream, turn, reply):
        target = Dropping(ledger) if turn.interface == "openai-responses" else ledger
        whole(target, upstream, turn, reply)

    chat, responses, messages = _three_ways(monkeypatch, record)
    _equivalent(chat, messages, "anthropic-messages")       # the untouched path still holds
    with pytest.raises(AssertionError):
        _equivalent(chat, responses, "openai-responses")
