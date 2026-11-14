"""The gateway's Anthropic Messages interface, replayed with no network.

Each test sends a recorded Messages request through the real handler function
(`gateway_messages.handle`) to a backend whose transport replays a recorded
upstream reply, then compares the answer field by field with the recorded
expectation. Upstream dialects: OpenAI-compatible chat, Anthropic, Gemini.

Wire formats, read 2026-11-13:
  https://platform.claude.com/docs/en/api/messages/create
  https://platform.claude.com/docs/en/build-with-claude/streaming
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
  https://platform.claude.com/docs/en/build-with-claude/token-counting
  https://code.claude.com/docs/en/llm-gateway-protocol.md (headers to forward,
      count_tokens is optional)
"""
import pytest

from harness import gateway_messages, gateway_turn
from harness.local_session import SessionLedger
from harness.messages_api import make_receipt
from harness.proposer import prompt_hash
from tests import gateway_messages_support as support
from tests.hosted_stream_fixtures import plain_object, stream_bytes


def _ask(monkeypatch, provider, request, *, plain=(), streams=(), headers=None):
    ledger = SessionLedger()
    backend = support.replayed(monkeypatch, provider, plain=plain, streams=streams)
    answer = gateway_messages.handle(support.load(request), headers or {}, ledger)
    return answer, backend, ledger


def _stripped(body: dict) -> dict:
    """A Message without the two fields the gateway makes fresh per reply."""
    return {key: value for key, value in body.items() if key not in ("id", "x_receipt")}


@pytest.mark.parametrize("provider, expected", [
    ("openai", "expected/openai_text.json"), ("gemini", "expected/gemini_text.json")])
def test_plain_text_is_a_message_object_field_by_field(monkeypatch, provider, expected):
    answer, _backend, ledger = _ask(monkeypatch, provider, "requests/text.json",
                                    plain=[plain_object(provider, "turn2")])
    assert answer.status == 200
    assert _stripped(answer.body) == support.load(expected)
    assert answer.body["id"].startswith("msg_")
    assert support.kinds(ledger) == ["endpoint_call"]


def test_receipt_recomputes_from_the_turn_and_the_reply(monkeypatch):
    answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                    plain=[plain_object("openai", "turn2")])
    text = "Wrote n.txt.\nNothing else changed."
    again = make_receipt({"prompt": "What changed?", "system": "", "max_new_tokens": 64,
                          "temperature": None, "seed": 0},
                         {"text": text, "seed": 0, "prompt_hash": prompt_hash("What changed?"),
                          "served_model": "gpt-5.3-codex-spark"}, "openai:gpt-5.3-codex-spark")
    assert answer.body["x_receipt"] == again
    assert answer.headers["x-receipt-id"] == again["receipt_id"]
    meta = ledger.entries[0].meta
    assert meta["response_sha"] == prompt_hash(text) == ledger.entries[0].content
    assert meta["prompt_sha"] == prompt_hash("What changed?")


def test_system_blocks_temperature_and_stop_reach_an_openai_upstream(monkeypatch):
    _answer, backend, _ledger = _ask(monkeypatch, "openai", "requests/system.json",
                                     plain=[plain_object("openai", "turn2")])
    assert backend.transport.requests[0]["body"] == support.load(
        "expected/openai_system.request.json")


def test_system_prompt_reaches_gemini_unchanged(monkeypatch):
    _answer, backend, _ledger = _ask(monkeypatch, "gemini", "requests/system.json",
                                     plain=[plain_object("gemini", "turn2")])
    sent = backend.transport.requests[0]["body"]
    assert sent["systemInstruction"] == {"parts": [{"text": "Be brief.\nAnswer in English."}]}
    assert sent["generationConfig"] == {"maxOutputTokens": 64, "temperature": 0.2,
                                        "stopSequences": ["END"]}


def test_tool_definitions_and_choice_reach_an_openai_upstream(monkeypatch):
    answer, backend, _ledger = _ask(monkeypatch, "openai", "requests/tools.json",
                                    plain=[plain_object("openai", "tool_call")])
    assert backend.transport.requests[0]["body"] == support.load(
        "expected/openai_tools.request.json")
    assert _stripped(answer.body) == support.load("expected/openai_tool.json")


def test_gemini_tool_call_comes_back_as_a_tool_use_block(monkeypatch):
    answer, _backend, _ledger = _ask(monkeypatch, "gemini", "requests/tools.json",
                                     plain=[plain_object("gemini", "function_call")])
    expected = support.load("expected/gemini_tool.json")
    made = answer.body["content"][1].pop("id")
    expected["content"][1].pop("id")
    assert made.startswith("toolu_") and len(made) > 12      # Gemini sends no call id
    assert _stripped(answer.body) == expected


@pytest.mark.parametrize("provider, expected", [
    ("openai", "expected/openai_tool_result.request.json"),
    ("gemini", "expected/gemini_tool_result.request.json")])
def test_tool_result_in_history_travels_in_the_upstream_shape(monkeypatch, provider, expected):
    answer, backend, _ledger = _ask(monkeypatch, provider, "requests/tool_result.json",
                                    plain=[plain_object(provider, "turn2")])
    assert answer.status == 200
    assert backend.transport.requests[0]["body"] == support.load(expected)


def test_neutral_turn_written_for_an_anthropic_upstream():
    from harness import gateway_messages_wire, gateway_turn_wire
    from tests.hosted_stream_fixtures import backend
    turn = gateway_messages_wire.parse(support.load("requests/tool_result.json"))
    upstream = gateway_turn.Upstream("anthropic", "anthropic", backend("anthropic"))
    url, headers, payload = gateway_turn_wire.request(turn, upstream)
    assert url.endswith("/v1/messages") and headers["x-api-key"] == "test-key"
    assert payload == support.load("expected/anthropic_tool_result.request.json")


def test_thinking_in_history_is_dropped_for_another_dialect(monkeypatch):
    _answer, backend, _ledger = _ask(monkeypatch, "openai", "requests/thinking_history.json",
                                     plain=[plain_object("openai", "turn2")])
    assert backend.transport.requests[0]["body"] == support.load(
        "expected/openai_tool_result.request.json")


def test_anthropic_upstream_gets_the_body_verbatim_with_only_the_model_replaced(monkeypatch):
    sent = support.load("requests/thinking_history.json")
    answer, backend, ledger = _ask(
        monkeypatch, "anthropic", "requests/thinking_history.json",
        plain=[support.load("upstream/anthropic_cached.json")],
        headers={"Anthropic-Version": "2023-06-01", "anthropic-beta": "extended-cache-ttl-x",
                 "x-api-key": support.TOKEN})
    seen = backend.transport.requests[0]
    assert seen["body"] == {**sent, "model": "claude-sonnet-5"}
    assert seen["body"]["messages"][1]["content"][0]["type"] == "thinking"
    assert seen["headers"]["anthropic-beta"] == "extended-cache-ttl-x"
    assert seen["headers"]["x-api-key"] == "test-key"       # never the client's gateway token
    assert support.TOKEN not in str(seen)
    upstream = support.load("upstream/anthropic_cached.json")
    assert {k: v for k, v in answer.body.items() if k != "x_receipt"} == upstream
    assert answer.body["usage"]["cache_read_input_tokens"] == 2051
    assert ledger.entries[0].meta["model_ref"] == "anthropic:claude-sonnet-5"


def test_usage_carries_the_cache_counts_under_the_messages_names(monkeypatch):
    answer, _backend, _ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                     plain=[support.load("upstream/openai_cached.json")])
    assert _stripped(answer.body) == support.load("expected/openai_cached.json")
    assert answer.body["usage"]["input_tokens"] + answer.body["usage"][
        "cache_read_input_tokens"] == 451        # the provider's prompt_tokens, not an estimate


def test_no_upstream_counts_means_zero_and_a_flag_never_an_estimate(monkeypatch):
    answer, _backend, _ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                     plain=[support.load("upstream/openai_no_usage.json")])
    assert answer.body["usage"]["input_tokens"] == answer.body["usage"]["output_tokens"] == 0
    assert answer.body["x_flywheel"] == {"usage_reported": False}


@pytest.mark.parametrize("request_name, upstream, expected", [
    ("requests/stream_text.json", "turn2", "expected/openai_stream_text.events.json"),
    ("requests/stream_tools.json", "tool_call", "expected/openai_stream_tool.events.json")])
def test_openai_stream_becomes_messages_events_in_order(monkeypatch, request_name, upstream,
                                                        expected):
    answer, backend, ledger = _ask(monkeypatch, "openai", request_name,
                                   streams=[stream_bytes("openai", upstream)])
    got = support.events(support.joined(answer.chunks))
    assert got[0][1]["message"].pop("id").startswith("msg_")
    receipt = got[-1][1].pop("x_receipt")
    want = support.load(expected)
    want[0][1]["message"].pop("id")
    assert got == want
    assert receipt["response_hash"] == ledger.entries[0].meta["response_sha"]
    assert backend.stream_transport.requests[0]["body"]["stream"] is True
    assert support.kinds(ledger) == ["endpoint_call"]


def test_gemini_stream_text_and_tool_call(monkeypatch):
    answer, _backend, ledger = _ask(monkeypatch, "gemini", "requests/stream_tools.json",
                                    streams=[stream_bytes("gemini", "function_call")])
    got = support.events(support.joined(answer.chunks))
    text = "".join(data["delta"]["text"] for name, data in got
                   if name == "content_block_delta" and data["delta"]["type"] == "text_delta")
    tool = [data for name, data in got if name == "content_block_start" and data["index"] == 1]
    assert text == "I will write the note."
    assert tool[0]["content_block"]["name"] == "write_file"
    assert got[-2][1]["delta"]["stop_reason"] == "tool_use"
    assert got[-2][1]["usage"]["input_tokens"] == 510 and got[-2][1]["usage"]["output_tokens"] == 36
    assert support.kinds(ledger) == ["endpoint_call"]


def test_anthropic_stream_is_forwarded_event_for_event(monkeypatch):
    recorded = stream_bytes("anthropic", "tool_use")
    answer, _backend, ledger = _ask(monkeypatch, "anthropic", "requests/stream_tools.json",
                                    streams=[recorded])
    out = support.joined(answer.chunks)
    head = recorded[: recorded.index(b"event: message_stop")]
    assert out.startswith(head)                 # byte for byte up to the last event
    last = support.events(out[len(head):])
    assert [name for name, _ in last] == ["message_stop"]
    assert last[0][1]["x_receipt"]["model_ref"] == "anthropic:claude-sonnet-5"
    assert ledger.entries[0].meta["response_sha"] == last[0][1]["x_receipt"]["response_hash"]


def test_count_tokens_is_forwarded_to_an_anthropic_upstream(monkeypatch):
    backend = support.replayed(monkeypatch, "anthropic",
                               plain=[support.load("upstream/anthropic_count.json")])
    body = {key: value for key, value in support.load("requests/tools.json").items()
            if key != "max_tokens"}
    answer = gateway_messages.count_tokens(body, {"anthropic-version": "2023-06-01"})
    assert (answer.status, answer.body) == (200, {"input_tokens": 14})
    seen = backend.transport.requests[0]
    assert seen["url"].endswith("/v1/messages/count_tokens")
    assert seen["body"] == {**body, "model": "claude-sonnet-5"}


def test_count_tokens_on_another_upstream_is_a_documented_not_found(monkeypatch):
    backend = support.replayed(monkeypatch, "openai")
    answer = gateway_messages.count_tokens(support.load("requests/text.json"), {})
    assert answer.status == 404
    assert answer.body["type"] == "error"
    assert answer.body["error"]["type"] == "not_found_error"
    assert "input_tokens" not in answer.body and backend.transport.requests == []


def test_upstream_rule_keeps_or_replaces_the_client_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-a-real-credential")
    kept = gateway_turn.resolve_upstream("claude-opus-5", {"FLYWHEEL_GATEWAY_UPSTREAM": "anthropic"})
    forced = gateway_turn.resolve_upstream(
        "claude-opus-5", {"FLYWHEEL_GATEWAY_UPSTREAM": "ollama:qwen2.5:1.5b"})
    named = gateway_turn.resolve_upstream("ollama:llama3", {})
    assert (kept.name, kept.dialect, kept.backend.model) == ("anthropic", "anthropic", "claude-opus-5")
    assert (forced.name, forced.dialect, forced.backend.model) == ("ollama", "openai", "qwen2.5:1.5b")
    assert (named.name, named.backend.model) == ("ollama", "llama3")
