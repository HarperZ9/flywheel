"""Client compatibility: the official `openai` Python SDK against the gateway.

The SDK is pointed at a real gateway on a loopback port with a token that is
plainly a test value. The gateway talks to a loopback stub upstream that
replays recorded OpenAI-compatible replies. No provider is called. The SDK is
a test-only import: the tests are skipped where it is not installed, and it is
in no dependency list.

The last two tests check the gateway's bodies and events against the SDK's own
models, which are generated from OpenAI's published spec. A missing or
mistyped required field fails validation.

Read 2026-11-14:
  https://raw.githubusercontent.com/openai/openai-python/main/README.md
      `OpenAI(api_key=..., base_url=...)`, OPENAI_API_KEY, OPENAI_BASE_URL,
      `client.responses.create`, `stream=True`, the status to exception table
  openai 2.36.0, `types/responses` (the Response and stream event models) and
      `_streaming.py` (an `error` event is yielded, not raised)
  https://developers.openai.com/api/docs/guides/function-calling
"""
import json

import pytest

from tests import gateway_responses_support as support
from tests.hosted_stream_fixtures import plain_object, stream_bytes

openai = pytest.importorskip("openai")

TOOL = support.load("requests/tools.json")["tools"][0]
TEXT = "Wrote n.txt.\nNothing else changed."
MODEL = "gpt-5.3-codex"


def _client(url, api_key=support.TOKEN):
    return openai.OpenAI(base_url=f"{url}/v1", api_key=api_key, max_retries=0, timeout=30)


@pytest.fixture
def served(monkeypatch, tmp_path):
    """start(answers) points a gateway at a stub upstream with those answers."""
    opened = []

    def start(answers, provider="openai"):
        upstream = support.Upstream(answers).__enter__()
        gate = support.gateway_server(monkeypatch, tmp_path)
        url, ledger = gate.__enter__()
        opened.extend([gate, upstream])
        support.point_at(monkeypatch, provider, upstream.url)
        return url, upstream, ledger
    yield start
    for item in opened:
        item.__exit__(None, None, None)


def test_responses_create(served):
    url, upstream, ledger = served([support.json_answer(plain_object("openai", "turn2"))])
    response = _client(url).responses.create(
        model=MODEL, instructions="Be brief.", input="What changed?", max_output_tokens=64)
    assert response.object == "response" and response.status == "completed"
    assert response.output_text == TEXT
    assert response.output[0].type == "message" and response.output[0].role == "assistant"
    assert (response.usage.input_tokens, response.usage.output_tokens) == (451, 9)
    assert response.usage.total_tokens == 460
    assert response.model == "gpt-5.3-codex-spark"          # the model that served it
    assert upstream.requests[0]["body"]["messages"][0] == {"role": "system", "content": "Be brief."}
    assert upstream.requests[0]["headers"]["authorization"] == "Bearer test-key"
    assert support.kinds(ledger) == ["endpoint_call"]


def test_cached_tokens_reach_the_sdk_usage_object(served):
    cached = support.upstream_load("upstream/openai_cached.json")
    url, _upstream, _ledger = served([support.json_answer(cached)])
    usage = _client(url).responses.create(model=MODEL, input="What changed?").usage
    assert (usage.input_tokens, usage.input_tokens_details.cached_tokens) == (451, 400)


def test_stream_true_yields_the_events_in_order(served):
    url, _upstream, ledger = served([support.stream_answer(stream_bytes("openai", "turn2"))])
    events = list(_client(url).responses.create(model=MODEL, input="What changed?",
                                                stream=True))
    names = [event.type for event in events]
    pieces = [event.delta for event in events if event.type == "response.output_text.delta"]
    assert names[:4] == ["response.created", "response.in_progress",
                         "response.output_item.added", "response.content_part.added"]
    assert names[-4:] == ["response.output_text.done", "response.content_part.done",
                          "response.output_item.done", "response.completed"]
    assert pieces == ["Wrote n.t", "xt.\nNothi", "ng else c", "hanged."]     # as the upstream sent
    assert [event.sequence_number for event in events] == list(range(len(events)))
    final = events[-1].response
    assert final.status == "completed" and final.output_text == TEXT
    assert (final.usage.input_tokens, final.usage.output_tokens) == (451, 9)
    assert support.kinds(ledger) == ["endpoint_call"]


def test_stream_helper_assembles_a_function_call(served):
    url, _upstream, _ledger = served([support.stream_answer(stream_bytes("openai", "tool_call"))])
    with _client(url).responses.stream(model=MODEL, input="write a note",
                                       tools=[TOOL]) as stream:
        seen = [event.type for event in stream]
        final = stream.get_final_response()
    call = final.output[1]
    assert "response.function_call_arguments.done" in seen
    assert (call.type, call.name, call.call_id) == (
        "function_call", "write_file", "call_fixtureWrite01")
    assert json.loads(call.arguments) == {"path": "n.txt", "content": "hi"}


def test_function_call_round_trip(served):
    url, upstream, ledger = served([support.json_answer(plain_object("openai", "tool_call")),
                                    support.json_answer(plain_object("openai", "turn2"))])
    client = _client(url)
    history = [{"role": "user", "content": "write a note"}]
    first = client.responses.create(model=MODEL, input=history, tools=[TOOL])
    call = next(item for item in first.output if item.type == "function_call")
    assert (call.call_id, call.name) == ("call_fixtureWrite01", "write_file")
    assert json.loads(call.arguments) == {"path": "n.txt", "content": "hi"}
    history += [item.model_dump(exclude_none=True) for item in first.output]
    history.append({"type": "function_call_output", "call_id": call.call_id,
                    "output": "wrote 2 bytes"})
    second = client.responses.create(model=MODEL, input=history, tools=[TOOL])
    assert second.output_text == TEXT
    sent = upstream.requests[1]["body"]["messages"]
    assert sent[1]["tool_calls"][0]["id"] == "call_fixtureWrite01"
    assert sent[2] == {"role": "tool", "tool_call_id": "call_fixtureWrite01",
                       "content": "wrote 2 bytes"}
    assert support.kinds(ledger) == ["endpoint_call", "endpoint_call"]
    assert ledger.verify()


def test_errors_map_to_the_sdk_typed_exceptions(served, monkeypatch):
    limited = support.json_answer(support.upstream_load("upstream/openai_rate_limited.json"), 429)
    url, upstream, ledger = served([limited])
    client = _client(url)
    with pytest.raises(openai.RateLimitError) as limit:
        client.responses.create(model=MODEL, input="What changed?")
    assert limit.value.status_code == 429 and limit.value.code == "rate_limit_exceeded"
    with pytest.raises(openai.BadRequestError) as stored:
        client.responses.create(model=MODEL, input="hi", previous_response_id="resp_abc")
    assert stored.value.param == "previous_response_id"
    assert stored.value.type == "invalid_request_error"
    with pytest.raises(openai.BadRequestError) as orphan:
        client.responses.create(**support.load("requests/orphan_output.json"))
    assert "call_id" in orphan.value.message
    with pytest.raises(openai.AuthenticationError):
        _client(url, api_key="wrong-test-token").responses.create(model=MODEL, input="hi")
    monkeypatch.delenv("FLYWHEEL_GATEWAY_UPSTREAM")
    with pytest.raises(openai.NotFoundError) as unknown:
        client.responses.create(model="no-such-model", input="hi")
    assert unknown.value.param == "model"
    assert len(upstream.requests) == 1                      # only the rate-limited call went out
    assert support.kinds(ledger) == ["endpoint_call_failed"]


def test_stream_cut_mid_event_reaches_the_sdk_as_response_failed(served):
    cut = support.upstream_raw("upstream/openai_cut.sse")
    url, _upstream, ledger = served([support.stream_answer(cut)])
    events = list(_client(url).responses.create(model=MODEL, input="What changed?",
                                                stream=True))
    last = events[-1]
    assert last.type == "response.failed" and last.response.status == "failed"
    assert last.response.error.code == "server_error"
    assert "stream" in last.response.error.message
    assert "response.completed" not in [event.type for event in events]
    assert support.kinds(ledger) == ["endpoint_call_failed"]


def _strict(model, value):
    """Validate against the SDK model with no field left to its default."""
    from pydantic import TypeAdapter
    made = TypeAdapter(model).validate_python(value)
    given = made.model_dump(exclude_unset=True, by_alias=True)
    return made, given


@pytest.mark.parametrize("name", ["openai_text", "openai_tool", "openai_cached",
                                  "anthropic_text", "gemini_text"])
def test_recorded_response_objects_validate_against_the_sdk_model(name):
    from openai.types.responses import Response
    body = {**support.load(f"expected/{name}.json"), "created_at": 1794268190}
    made, given = _strict(Response, body)
    required = {key for key, field in Response.model_fields.items() if field.is_required()}
    assert required <= set(body), f"missing required fields: {required - set(body)}"
    assert made.usage.total_tokens == body["usage"]["total_tokens"]
    assert [item.type for item in made.output] == [item["type"] for item in body["output"]]
    assert set(given["usage"]) == set(body["usage"])
    with pytest.raises(Exception, match="usage|total_tokens"):
        _strict(Response, {**body, "usage": {"input_tokens": 1}})   # a dropped count fails


@pytest.mark.parametrize("name", ["openai_stream_text", "openai_stream_tool"])
def test_recorded_stream_events_validate_against_the_sdk_models(name):
    from openai.types.responses import ResponseStreamEvent
    for kind, data in support.load(f"expected/{name}.events.json"):
        if "response" in data:
            data = {**data, "response": {**data["response"], "created_at": 1794268190}}
        made, _given = _strict(ResponseStreamEvent, data)
        assert made.type == kind == data["type"]
        fields = {key for key, field in type(made).model_fields.items() if field.is_required()}
        assert fields <= set(data), f"{kind} lacks {fields - set(data)}"
