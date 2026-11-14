"""The gateway's OpenAI Responses interface, replayed with no network.

Each test sends a recorded Responses request through the real handler function
(`gateway_responses.handle`) to a backend whose transport replays a recorded
upstream reply, then compares the answer field by field with the recorded
expectation. Upstream dialects: OpenAI-compatible chat, Anthropic, Gemini.

Wire format, read 2026-11-14. platform.openai.com refused the fetch (403), so:
  https://github.com/openai/openai-openapi (manual_spec branch, openapi.yaml):
      CreateResponse, Response, ResponseUsage, FunctionToolCall,
      FunctionToolCallOutput, the createResponse streaming example (the event
      order), ResponseFunctionCallArgumentsDeltaEvent and ...DoneEvent
  openai Python SDK 2.36.0, types/responses (generated from that spec):
      `sequence_number` on every event, `logprobs` on the text events
  https://developers.openai.com/api/docs/guides/function-calling
      the function tool, `function_call` and `function_call_output` shapes,
      and the four stream events of a function call
  https://developers.openai.com/api/docs/guides/streaming-responses
      the event names by group
"""
import pytest

from harness import gateway_responses, gateway_responses_wire, gateway_turn, gateway_turn_wire
from harness.local_session import SessionLedger
from harness.messages_api import make_receipt
from harness.proposer import prompt_hash
from tests import gateway_responses_support as support
from tests.hosted_stream_fixtures import NATIVE, backend as replay, plain_object, stream_bytes

TEXT = "Wrote n.txt.\nNothing else changed."


def _ask(monkeypatch, provider, request, *, plain=(), streams=()):
    ledger = SessionLedger()
    backend = support.replayed(monkeypatch, provider, plain=plain, streams=streams)
    body = support.load(request) if isinstance(request, str) else request
    return gateway_responses.handle(body, {}, ledger), backend, ledger


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
def test_plain_text_is_a_response_object_field_by_field(monkeypatch, provider):
    answer, _backend, ledger = _ask(monkeypatch, provider, "requests/text.json",
                                    plain=[plain_object(provider, "turn2")])
    assert answer.status == 200
    assert support.normal(answer.body) == support.load(f"expected/{provider}_text.json")
    assert answer.body["id"].startswith("resp_") and answer.body["created_at"] > 0
    assert answer.body["output"][0]["content"][0]["text"] == TEXT
    assert support.kinds(ledger) == ["endpoint_call"]
    assert ledger.entries[0].meta["interface"] == "openai-responses"


def test_receipt_recomputes_from_the_turn_and_the_reply(monkeypatch):
    answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                    plain=[plain_object("openai", "turn2")])
    again = make_receipt({"prompt": "What changed?", "system": "", "max_new_tokens": 64,
                          "temperature": None, "seed": 0},
                         {"text": TEXT, "seed": 0, "prompt_hash": prompt_hash("What changed?"),
                          "served_model": "gpt-5.3-codex-spark"}, "openai:gpt-5.3-codex-spark")
    assert answer.body["x_receipt"] == again
    assert answer.headers["x-receipt-id"] == again["receipt_id"]
    meta = ledger.entries[0].meta
    assert meta["response_sha"] == prompt_hash(TEXT) == ledger.entries[0].content
    assert meta["prompt_sha"] == prompt_hash("What changed?")


def test_instructions_and_a_developer_message_reach_the_upstream_as_system(monkeypatch):
    answer, backend, _ledger = _ask(monkeypatch, "openai", "requests/instructions.json",
                                    plain=[plain_object("openai", "turn2")])
    assert backend.transport.requests[0]["body"] == support.load(
        "expected/openai_instructions.request.json")
    assert answer.body["instructions"] == "Be brief."        # echoed as sent
    assert (answer.body["temperature"], answer.body["top_p"]) == (0.2, 0.9)
    assert answer.body["store"] is False                     # nothing is stored


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_function_tools_go_out_and_a_function_call_comes_back(monkeypatch, provider):
    answer, backend, _ledger = _ask(monkeypatch, provider, "requests/tools.json",
                                    plain=[plain_object(provider, NATIVE[provider])])
    assert backend.transport.requests[0]["body"] == support.load(
        f"expected/{provider}_tools.request.json")
    assert support.normal(answer.body) == support.load(f"expected/{provider}_tool.json")
    call = answer.body["output"][1]
    assert (call["type"], call["name"]) == ("function_call", "write_file")
    assert call["arguments"] == '{"path": "n.txt", "content": "hi"}'


def test_gemini_function_call_gets_a_call_id_the_client_can_answer(monkeypatch):
    answer, _backend, _ledger = _ask(monkeypatch, "gemini", "requests/tools.json",
                                     plain=[plain_object("gemini", "function_call")])
    call = answer.body["output"][1]
    assert (call["type"], call["name"], call["status"]) == (
        "function_call", "write_file", "completed")
    assert call["call_id"].startswith("toolu_") and len(call["call_id"]) > 12
    assert answer.body["output"][0]["content"][0]["text"] == "I will write the note."


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_function_call_output_in_history_travels_in_the_upstream_shape(monkeypatch, provider):
    answer, backend, _ledger = _ask(monkeypatch, provider, "requests/tool_result.json",
                                    plain=[plain_object(provider, "turn2")])
    assert answer.status == 200
    assert backend.transport.requests[0]["body"] == support.load(
        f"expected/{provider}_tool_result.request.json")


def test_history_written_for_an_anthropic_upstream():
    turn, _echo = gateway_responses_wire.parse(support.load("requests/tool_result.json"))
    upstream = gateway_turn.Upstream("anthropic", "anthropic", replay("anthropic"))
    url, headers, payload = gateway_turn_wire.request(turn, upstream)
    assert url.endswith("/v1/messages") and headers["x-api-key"] == "test-key"
    assert payload == support.load("expected/anthropic_tool_result.request.json")


def test_reasoning_items_in_history_are_dropped(monkeypatch):
    sent = support.load("requests/reasoning_history.json")
    assert any(item.get("type") == "reasoning" for item in sent["input"])
    answer, backend, _ledger = _ask(monkeypatch, "openai", sent,
                                    plain=[plain_object("openai", "turn2")])
    assert answer.status == 200
    assert backend.transport.requests[0]["body"] == support.load(
        "expected/openai_tool_result.request.json")
    assert "opaque-fixture-bytes" not in str(backend.transport.requests)


def test_cached_tokens_are_reported_inside_input_tokens(monkeypatch):
    upstream = support.upstream_load("upstream/openai_cached.json")
    answer, _backend, _ledger = _ask(monkeypatch, "openai", "requests/text.json",
                                     plain=[upstream])
    assert support.normal(answer.body) == support.load("expected/openai_cached.json")
    usage = answer.body["usage"]
    assert usage["input_tokens"] == upstream["usage"]["prompt_tokens"] == 451
    assert usage["input_tokens_details"] == {"cached_tokens": 400}
    assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"] == 460
    assert "x_flywheel" not in answer.body


def test_anthropic_cache_counts_are_added_back_into_input_tokens(monkeypatch):
    upstream = support.upstream_load("upstream/anthropic_cached.json")
    answer, _backend, _ledger = _ask(monkeypatch, "anthropic", "requests/text.json",
                                     plain=[upstream])
    assert support.normal(answer.body) == support.load("expected/anthropic_cached.json")
    sent = upstream["usage"]
    assert answer.body["usage"]["input_tokens"] == (
        sent["input_tokens"] + sent["cache_read_input_tokens"]
        + sent["cache_creation_input_tokens"]) == 2363
    assert answer.body["usage"]["input_tokens_details"]["cached_tokens"] == 2051


def test_no_upstream_counts_means_zero_and_a_flag_never_an_estimate(monkeypatch):
    answer, _backend, _ledger = _ask(
        monkeypatch, "openai", "requests/text.json",
        plain=[support.upstream_load("upstream/openai_no_usage.json")])
    usage = answer.body["usage"]
    assert usage["input_tokens"] == usage["output_tokens"] == usage["total_tokens"] == 0
    assert answer.body["x_flywheel"] == {"usage_reported": False,
                                         "cached_tokens_reported": False}


def test_a_reply_cut_by_the_token_limit_is_incomplete(monkeypatch):
    cut = plain_object("openai", "turn2")
    cut["choices"][0]["finish_reason"] = "length"
    answer, _backend, ledger = _ask(monkeypatch, "openai", "requests/text.json", plain=[cut])
    assert answer.body["status"] == "incomplete"
    assert answer.body["incomplete_details"] == {"reason": "max_output_tokens"}
    assert answer.body["output"][0]["status"] == "incomplete"
    assert support.kinds(ledger) == ["endpoint_call"]


@pytest.mark.parametrize("request_name, upstream, expected", [
    ("requests/stream_text.json", "turn2", "expected/openai_stream_text.events.json"),
    ("requests/stream_tools.json", "tool_call", "expected/openai_stream_tool.events.json")])
def test_openai_stream_becomes_responses_events_in_order(monkeypatch, request_name, upstream,
                                                         expected):
    answer, backend, ledger = _ask(monkeypatch, "openai", request_name,
                                   streams=[stream_bytes("openai", upstream)])
    got = support.events(support.joined(answer.chunks))
    receipt = got[-1][1]["response"]["x_receipt"]
    assert support.normal(got) == support.load(expected)
    assert [data["sequence_number"] for _name, data in got] == list(range(len(got)))
    assert all(name == data["type"] for name, data in got)
    assert receipt["response_hash"] == ledger.entries[0].meta["response_sha"]
    assert backend.stream_transport.requests[0]["body"]["stream"] is True
    assert support.kinds(ledger) == ["endpoint_call"]


@pytest.mark.parametrize("provider, upstream, text, counts", [
    ("anthropic", "tool_use", "I will write the note.", None),
    ("gemini", "function_call", "I will write the note.", (510, 36))])
def test_other_dialects_stream_text_and_a_function_call(monkeypatch, provider, upstream, text,
                                                        counts):
    answer, _backend, ledger = _ask(monkeypatch, provider, "requests/stream_tools.json",
                                    streams=[stream_bytes(provider, upstream)])
    got = support.events(support.joined(answer.chunks))
    names = [name for name, _data in got]
    shown = "".join(data["delta"] for name, data in got
                    if name == "response.output_text.delta")
    done = [data for name, data in got if name == "response.function_call_arguments.done"]
    final = got[-1][1]["response"]
    assert names[:2] == ["response.created", "response.in_progress"]
    assert names[-1] == "response.completed" and shown == text
    assert (done[0]["name"], done[0]["output_index"]) == ("write_file", 1)
    assert done[0]["arguments"] == '{"path": "n.txt", "content": "hi"}'
    assert [item["type"] for item in final["output"]] == ["message", "function_call"]
    if counts:
        assert (final["usage"]["input_tokens"], final["usage"]["output_tokens"]) == counts
    assert final["usage"]["output_tokens"] > 0
    assert support.kinds(ledger) == ["endpoint_call"]


def test_a_tool_round_trip_through_the_handler(monkeypatch):
    backend = support.replayed(monkeypatch, "openai", plain=[
        plain_object("openai", "tool_call"), plain_object("openai", "turn2")])
    ledger, request = SessionLedger(), support.load("requests/tools.json")
    first = gateway_responses.handle(request, {}, ledger)
    call = first.body["output"][1]
    history = [{"role": "user", "content": request["input"]}, *first.body["output"],
               {"type": "function_call_output", "call_id": call["call_id"],
                "output": "wrote 2 bytes"}]
    second = gateway_responses.handle({**request, "input": history, "tool_choice": "auto"},
                                      {}, ledger)
    sent = backend.transport.requests[1]["body"]["messages"]
    assert second.body["output"][0]["content"][0]["text"] == TEXT
    assert sent[1]["tool_calls"][0]["id"] == call["call_id"] == "call_fixtureWrite01"
    assert sent[2] == {"role": "tool", "tool_call_id": "call_fixtureWrite01",
                       "content": "wrote 2 bytes"}
    assert support.kinds(ledger) == ["endpoint_call", "endpoint_call"] and ledger.verify()
