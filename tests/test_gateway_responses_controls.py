"""Controls for the gateway's Responses interface: what must be refused or fail.

Each test pairs a refusal or a failure with what must not happen beside it: no
upstream request, no completed ledger entry, no key in the answer.

Wire format, read 2026-11-14. platform.openai.com refused the fetch (403), so:
  https://github.com/openai/openai-openapi (manual_spec branch, openapi.yaml):
      Error and ErrorResponse (`{"error": {"message", "type", "param",
      "code"}}`), ResponseFailedEvent, ResponseErrorEvent, ResponseUsage
  openai Python SDK 2.36.0, types/responses: response_failed_event,
      response_error_event, response_error (code `server_error`)
  https://developers.openai.com/api/docs/guides/error-codes
      `invalid_request_error`, `rate_limit_error`
"""
import io
import logging

import pytest

from harness import (gateway_interfaces, gateway_responses, gateway_responses_reply,
                     gateway_turn)
from harness.local_session import SessionLedger
from tests import gateway_responses_support as support
from tests.hosted_stream_fixtures import plain_object, stream_bytes


def _ask(monkeypatch, provider, body, *, plain=(), streams=(), ledger=None):
    ledger = SessionLedger() if ledger is None else ledger
    backend = support.replayed(monkeypatch, provider, plain=plain, streams=streams)
    body = support.load(body) if isinstance(body, str) else body
    return gateway_responses.handle(body, {}, ledger), backend, ledger


_is_error = support.is_error


@pytest.mark.parametrize("provider, cut", [("openai", "upstream/openai_cut.sse"),
                                           ("anthropic", "upstream/anthropic_cut.sse")])
def test_stream_cut_mid_event_ends_with_response_failed_and_a_failed_entry(
        monkeypatch, provider, cut):
    answer, _backend, ledger = _ask(monkeypatch, provider, "requests/stream_text.json",
                                    streams=[support.upstream_raw(cut)])
    got = support.events(support.joined(answer.chunks))
    names = [name for name, _data in got]
    failed = got[-1][1]
    assert names[-1] == "response.failed" and failed["sequence_number"] == len(got) - 1
    assert failed["response"]["status"] == "failed" and failed["response"]["output"] == []
    assert failed["response"]["error"]["code"] == "server_error"
    assert "stream" in failed["response"]["error"]["message"]
    assert "response.completed" not in names and "x_receipt" not in failed["response"]
    assert "response.output_text.delta" in names                     # text had been shown
    assert support.kinds(ledger) == ["endpoint_call_failed"]         # and no completed entry
    assert ledger.entries[0].meta["reason"] == "stream_incomplete"
    assert "response_sha" not in ledger.entries[0].meta


def test_client_that_leaves_mid_stream_gets_a_failed_entry(monkeypatch):
    answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/stream_text.json",
                                    streams=[stream_bytes("openai", "turn2")])
    chunks = iter(answer.chunks)
    assert b"response.created" in next(chunks) and b"response.in_progress" in next(chunks)
    assert b"response.output_item.added" in next(chunks)
    answer.chunks.close()
    assert support.kinds(ledger) == ["endpoint_call_failed"]
    assert ledger.entries[0].meta["reason"] == "client_disconnected"


class _Handler:
    """The parts of the HTTP handler `gateway_interfaces.send` touches."""

    def __init__(self):
        self.wfile, self.sent = io.BytesIO(), []

    def send_response(self, status):
        self.sent.append(status)

    def send_header(self, name, value):
        self.sent.append((name, value))

    def _cors(self):
        pass

    def end_headers(self):
        pass


def _breaks():
    yield b"event: first\ndata: {}\n\n"
    raise RuntimeError("boom")


def test_a_fault_after_the_headers_uses_the_error_event_of_the_right_interface():
    events = gateway_responses_reply.Events()
    events.write("response.created")
    ours, theirs = _Handler(), _Handler()
    gateway_interfaces.send(ours, gateway_turn.Response(200, chunks=_breaks(),
                                                        fault=events.fault))
    gateway_interfaces.send(theirs, gateway_turn.Response(200, chunks=_breaks()))
    last = support.events(ours.wfile.getvalue())[-1]
    assert last[0] == "error"
    assert last[1] == {"type": "error", "sequence_number": 1, "code": "server_error",
                       "message": "internal error: RuntimeError", "param": None}
    messages = support.events(theirs.wfile.getvalue())[-1]
    assert messages[0] == "error" and messages[1]["error"]["type"] == "api_error"
    assert "sequence_number" not in messages[1]              # the Messages error event


def test_upstream_reply_that_claims_a_tool_result_is_refused(monkeypatch):
    reply = plain_object("openai", "turn2")
    reply["choices"][0]["message"].update(role="tool", tool_call_id="call_fixtureWrite01")
    answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/text.json", plain=[reply])
    assert _is_error(answer, 502, "server_error")
    assert "tool result" in answer.body["error"]["message"]
    assert support.kinds(ledger) == ["endpoint_call_failed"]
    assert ledger.entries[0].meta["reason"] == "tool_result_claimed"


def test_openai_upstream_error_keeps_its_body_and_is_logged_without_the_key(monkeypatch, caplog):
    echoed = support.upstream_load("upstream/openai_rate_limited.json")
    echoed["error"]["message"] += " for key sk-proj-" + "A" * 32     # key-shaped, not a key
    with caplog.at_level(logging.WARNING, logger="harness.gateway_turn"):
        answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                        plain=[(429, echoed)])
    assert answer.status == 429 and set(answer.body) == {"error"}
    assert answer.body["error"]["code"] == "rate_limit_exceeded"     # the upstream's own
    assert answer.body["error"]["message"].startswith("Rate limit reached for requests")
    assert support.kinds(ledger) == ["endpoint_call_failed"]
    assert ledger.entries[0].meta["reason"] == "upstream_status_429"
    assert "upstream_status_429" in caplog.text                # logged with context
    assert "A" * 32 not in caplog.text + str(answer.body)


@pytest.mark.parametrize("status, kind", [(529, "server_error"), (429, "rate_limit_error")])
def test_another_dialect_error_is_rewritten_in_the_openai_shape(monkeypatch, status, kind):
    sent = support.upstream_load("upstream/anthropic_overloaded.json")
    answer, _backend, ledger = _ask(monkeypatch, "anthropic", "requests/text.json",
                                    plain=[(status, sent)])
    assert _is_error(answer, status, kind)
    assert "type" not in answer.body                          # not the Messages error body
    assert support.kinds(ledger) == ["endpoint_call_failed"]


def _conforms(body: dict, upstream: dict) -> None:
    """The conformance check on usage: the provider's own counts, as integers."""
    usage = body.get("usage")
    assert isinstance(usage, dict), "a Response must carry usage"
    assert usage.get("input_tokens") == upstream["usage"]["prompt_tokens"]
    assert usage.get("output_tokens") == upstream["usage"]["completion_tokens"]
    assert usage.get("total_tokens") == upstream["usage"]["total_tokens"]
    assert type(usage["input_tokens_details"]["cached_tokens"]) is int
    assert type(usage["output_tokens_details"]["reasoning_tokens"]) is int


def test_usage_passes_the_conformance_check(monkeypatch):
    upstream = plain_object("openai", "turn2")
    answer, _backend, _ledger = _ask(monkeypatch, "openai", "requests/text.json", plain=[upstream])
    _conforms(answer.body, upstream)


@pytest.mark.parametrize("dropped", [
    lambda reply: None,
    lambda reply: {"input_tokens": 0, "input_tokens_details": {"cached_tokens": 0},
                   "output_tokens": 0, "output_tokens_details": {"reasoning_tokens": 0},
                   "total_tokens": 0}])
def test_handler_that_drops_usage_fails_the_conformance_check(monkeypatch, dropped):
    monkeypatch.setattr(gateway_responses_reply, "usage", dropped)
    upstream = plain_object("openai", "turn2")
    answer, _backend, _ledger = _ask(monkeypatch, "openai", "requests/text.json", plain=[upstream])
    with pytest.raises(AssertionError):
        _conforms(answer.body, upstream)


def test_reply_is_not_served_when_no_ledger_entry_can_be_written(monkeypatch):
    support.replayed(monkeypatch, "openai", plain=[plain_object("openai", "turn2")])
    with pytest.raises(RuntimeError, match="ledger"):
        gateway_responses.handle(support.load("requests/text.json"), {}, None)


def test_served_request_with_no_ledger_entry_fails_the_check(monkeypatch):
    def served_and_ledgered(answer, ledger):
        assert answer.status == 200
        assert support.kinds(ledger) == ["endpoint_call"], "a served call must be on the ledger"

    answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                    plain=[plain_object("openai", "turn2")])
    served_and_ledgered(answer, ledger)
    monkeypatch.setattr(gateway_turn, "record", lambda *args: None)     # the entry is lost
    answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                    plain=[plain_object("openai", "turn2")])
    with pytest.raises(AssertionError, match="ledger"):
        served_and_ledgered(answer, ledger)


def test_endpoint_without_a_credential_is_refused_by_presence_only(monkeypatch):
    monkeypatch.setattr("harness.endpoints._credential", lambda env, direct: "")
    answer = gateway_responses.handle({"model": "anthropic", "input": "hi"}, {}, SessionLedger(), environ={})
    assert _is_error(answer, 400, "invalid_request_error")
    assert "no credential present" in answer.body["error"]["message"]
