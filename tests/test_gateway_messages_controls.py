"""Controls for the gateway's Messages interface: what must be refused or fail.

Each test pairs a refusal or a failure with what must not happen beside it: no
upstream request, no completed ledger entry, no key in the answer.

Wire formats, read 2026-11-13:
  https://platform.claude.com/docs/en/api/errors (error body, status to type)
  https://platform.claude.com/docs/en/build-with-claude/streaming (`event: error`)
  https://platform.claude.com/docs/en/api/messages/create (required fields, usage)
"""
import logging

import pytest

from harness import gateway_messages, gateway_messages_wire, gateway_turn
from harness.local_session import SessionLedger
from tests import gateway_messages_support as support
from tests.hosted_stream_fixtures import plain_object, stream_bytes


def _ask(monkeypatch, provider, body, *, plain=(), streams=(), ledger=None):
    ledger = SessionLedger() if ledger is None else ledger
    backend = support.replayed(monkeypatch, provider, plain=plain, streams=streams)
    body = support.load(body) if isinstance(body, str) else body
    return gateway_messages.handle(body, {}, ledger), backend, ledger


def _nothing_sent(backend) -> bool:
    return backend.transport.requests == [] and backend.stream_transport.requests == []


def _is_error(answer, status: int, kind: str) -> bool:
    body = answer.body
    return (answer.status == status and body["type"] == "error"
            and body["error"]["type"] == kind and isinstance(body["error"]["message"], str)
            and set(body) == {"type", "error", "request_id"})


MALFORMED = [
    ({"model": "claude-sonnet-5", "messages": [{"role": "user", "content": "hi"}]}, "max_tokens"),
    ({"model": "claude-sonnet-5", "max_tokens": 0, "messages": [{"role": "user", "content": "hi"}]},
     "max_tokens"),
    ({"model": "claude-sonnet-5", "max_tokens": 8, "messages": []}, "messages"),
    ({"max_tokens": 8, "messages": [{"role": "user", "content": "hi"}]}, "model"),
    ({"model": "claude-sonnet-5", "max_tokens": 8, "messages": [{"role": "system", "content": "x"}]},
     "messages.0.role"),
    ({"model": "claude-sonnet-5", "max_tokens": 8, "messages": [{"role": "user", "content": 7}]},
     "messages.0.content"),
    ({"model": "claude-sonnet-5", "max_tokens": 8, "tools": [{"name": "t"}],
      "messages": [{"role": "user", "content": "hi"}]}, "tools.0"),
    ({"model": "claude-sonnet-5", "max_tokens": 8, "tool_choice": {"type": "sometimes"},
      "messages": [{"role": "user", "content": "hi"}]}, "tool_choice"),
    ({"model": "claude-sonnet-5", "max_tokens": 8, "temperature": "hot",
      "messages": [{"role": "user", "content": "hi"}]}, "temperature"),
]


@pytest.mark.parametrize("body, names", MALFORMED)
def test_malformed_request_is_refused_before_any_upstream_call(monkeypatch, body, names):
    answer, backend, ledger = _ask(monkeypatch, "openai", body,
                                   plain=[plain_object("openai", "turn2")])
    assert _is_error(answer, 400, "invalid_request_error")
    assert names in answer.body["error"]["message"]
    assert ledger.entries == []               # refused before the upstream: no entry at all
    assert _nothing_sent(backend)


def test_tool_result_the_conversation_never_produced_is_refused(monkeypatch):
    answer, backend, ledger = _ask(monkeypatch, "openai", "requests/orphan_result.json",
                                   plain=[plain_object("openai", "turn2")])
    assert _is_error(answer, 400, "invalid_request_error")
    assert "tool_use_id" in answer.body["error"]["message"]
    assert ledger.entries == [] and _nothing_sent(backend)


def test_orphan_tool_result_is_refused_for_an_anthropic_upstream_too(monkeypatch):
    answer, backend, _ledger = _ask(monkeypatch, "anthropic", "requests/orphan_result.json",
                                    plain=[plain_object("anthropic", "turn2")])
    assert _is_error(answer, 400, "invalid_request_error") and _nothing_sent(backend)


def test_image_is_refused_by_name_for_another_dialect(monkeypatch):
    answer, backend, ledger = _ask(monkeypatch, "openai", "requests/image.json",
                                   plain=[plain_object("openai", "turn2")])
    assert _is_error(answer, 400, "invalid_request_error")
    assert "'image'" in answer.body["error"]["message"]
    assert ledger.entries == [] and _nothing_sent(backend)


def test_image_goes_through_to_an_anthropic_upstream(monkeypatch):
    answer, backend, _ledger = _ask(monkeypatch, "anthropic", "requests/image.json",
                                    plain=[plain_object("anthropic", "turn2")])
    assert answer.status == 200
    assert backend.transport.requests[0]["body"]["messages"][0]["content"][0]["type"] == "image"


def test_unknown_model_with_no_upstream_set_is_not_found(monkeypatch):
    monkeypatch.delenv(gateway_turn.UPSTREAM_ENV, raising=False)
    ledger = SessionLedger()
    answer = gateway_messages.handle(support.load("requests/text.json"), {}, ledger, environ={})
    assert _is_error(answer, 404, "not_found_error")
    assert gateway_turn.UPSTREAM_ENV in answer.body["error"]["message"]
    assert ledger.entries == []


@pytest.mark.parametrize("model", ["claude-cli", "codex-cli:gpt-5", "opencode", "serve"])
def test_flattened_prompt_endpoints_are_refused(model):
    body = {**support.load("requests/text.json"), "model": model}
    answer = gateway_messages.handle(body, {}, SessionLedger(), environ={})
    assert _is_error(answer, 400, "invalid_request_error")
    assert "flattened prompt" in answer.body["error"]["message"]


@pytest.mark.parametrize("provider, cut", [("anthropic", "upstream/anthropic_cut.sse"),
                                           ("openai", "upstream/openai_cut.sse")])
def test_stream_cut_mid_event_is_a_stream_error_and_a_failed_entry(monkeypatch, provider, cut):
    answer, _backend, ledger = _ask(monkeypatch, provider, "requests/stream_text.json",
                                    streams=[support.raw(cut)])
    got = support.events(support.joined(answer.chunks))
    assert got[-1][0] == "error"
    assert got[-1][1]["type"] == "error" and got[-1][1]["error"]["type"] == "api_error"
    assert "message_stop" not in [name for name, _ in got]
    assert any(name == "content_block_delta" for name, _ in got)     # text had been shown
    assert support.kinds(ledger) == ["endpoint_call_failed"]         # and no completed entry
    assert ledger.entries[0].meta["reason"] == "stream_incomplete"
    assert "response_sha" not in ledger.entries[0].meta


def test_client_that_leaves_mid_stream_gets_a_failed_entry(monkeypatch):
    answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/stream_text.json",
                                    streams=[stream_bytes("openai", "turn2")])
    chunks = iter(answer.chunks)
    assert b"message_start" in next(chunks) and b"content_block_start" in next(chunks)
    answer.chunks.close()
    assert support.kinds(ledger) == ["endpoint_call_failed"]
    assert ledger.entries[0].meta["reason"] == "client_disconnected"


def test_upstream_reply_that_claims_a_tool_result_is_refused(monkeypatch):
    reply = plain_object("openai", "turn2")
    reply["choices"][0]["message"].update(role="tool", tool_call_id="call_fixtureWrite01")
    answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/text.json", plain=[reply])
    assert _is_error(answer, 502, "api_error")
    assert "tool result" in answer.body["error"]["message"]
    assert support.kinds(ledger) == ["endpoint_call_failed"]
    assert ledger.entries[0].meta["reason"] == "tool_result_claimed"


def test_upstream_rate_limit_keeps_its_status_and_is_logged_without_the_key(monkeypatch, caplog):
    echoed = support.load("upstream/openai_rate_limited.json")
    echoed["error"]["message"] += " for key sk-proj-" + "A" * 32     # key-shaped, not a key
    with caplog.at_level(logging.WARNING, logger="harness.gateway_turn"):
        answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                        plain=[(429, echoed)])
    assert _is_error(answer, 429, "rate_limit_error")
    assert support.kinds(ledger) == ["endpoint_call_failed"]
    assert ledger.entries[0].meta["reason"] == "upstream_status_429"
    assert "upstream_status_429" in caplog.text                # logged with context
    assert "A" * 32 not in caplog.text + str(answer.body)


def test_anthropic_upstream_error_body_goes_back_as_sent(monkeypatch):
    sent = support.load("upstream/anthropic_overloaded.json")
    answer, _backend, ledger = _ask(monkeypatch, "anthropic", "requests/text.json",
                                    plain=[(529, sent)])
    assert (answer.status, answer.body) == (529, sent)
    assert support.kinds(ledger) == ["endpoint_call_failed"]


def _conforms(body: dict, upstream: dict) -> None:
    """The conformance check on usage: the provider's own counts, as integers."""
    usage = body.get("usage")
    assert isinstance(usage, dict), "a Message must carry usage"
    assert usage.get("input_tokens") == upstream["usage"]["prompt_tokens"]
    assert usage.get("output_tokens") == upstream["usage"]["completion_tokens"]
    assert set(usage) >= {"cache_creation_input_tokens", "cache_read_input_tokens"}


def test_usage_passes_the_conformance_check(monkeypatch):
    upstream = plain_object("openai", "turn2")
    answer, _backend, _ledger = _ask(monkeypatch, "openai", "requests/text.json", plain=[upstream])
    _conforms(answer.body, upstream)


@pytest.mark.parametrize("dropped", [
    lambda reply: {},
    lambda reply: {"input_tokens": 0, "output_tokens": 0,
                   "cache_creation_input_tokens": None, "cache_read_input_tokens": None}])
def test_handler_that_drops_usage_fails_the_conformance_check(monkeypatch, dropped):
    monkeypatch.setattr(gateway_messages_wire, "usage", dropped)
    upstream = plain_object("openai", "turn2")
    answer, _backend, _ledger = _ask(monkeypatch, "openai", "requests/text.json", plain=[upstream])
    with pytest.raises(AssertionError):
        _conforms(answer.body, upstream)


def test_reply_is_not_served_when_no_ledger_entry_can_be_written(monkeypatch):
    support.replayed(monkeypatch, "openai", plain=[plain_object("openai", "turn2")])
    with pytest.raises(RuntimeError, match="ledger"):
        gateway_messages.handle(support.load("requests/text.json"), {}, None)


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
    body = {**support.load("requests/text.json"), "model": "anthropic"}
    answer = gateway_messages.handle(body, {}, SessionLedger(), environ={})
    assert _is_error(answer, 400, "invalid_request_error")
    assert "no credential present" in answer.body["error"]["message"]
