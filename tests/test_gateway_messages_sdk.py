"""Client compatibility: the official `anthropic` Python SDK against the gateway.

The SDK is pointed at a real gateway on a loopback port with a token that is
plainly a test value. The gateway talks to a loopback stub upstream that
replays recorded OpenAI-compatible replies. No provider is called. The SDK is
a test-only import: the test is skipped where it is not installed, and it is
in no dependency list.

Read 2026-11-13:
  https://platform.claude.com/docs/en/api/messages/create
  https://platform.claude.com/docs/en/build-with-claude/streaming
  https://platform.claude.com/docs/en/api/errors
  anthropic 0.95.0, `_client.py`: `base_url` (or ANTHROPIC_BASE_URL), `api_key`
      sent as X-Api-Key, `auth_token` sent as Authorization: Bearer
"""
import pytest

from tests import gateway_messages_support as support
from tests.hosted_stream_fixtures import plain_object, stream_bytes

anthropic = pytest.importorskip("anthropic")

TOOL = support.load("requests/tools.json")["tools"][0]


def _client(url, **credential):
    credential = credential or {"api_key": support.TOKEN}
    return anthropic.Anthropic(base_url=url, max_retries=0, timeout=30, **credential)


@pytest.fixture
def served(monkeypatch, tmp_path):
    """(start, state): start(answers) points a gateway at a stub with those answers."""
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


@pytest.mark.parametrize("credential", [{"api_key": support.TOKEN},
                                        {"auth_token": support.TOKEN}])
def test_messages_create(served, credential):
    url, upstream, ledger = served([support.json_answer(plain_object("openai", "turn2"))])
    message = _client(url, **credential).messages.create(
        model="claude-sonnet-5", max_tokens=64, system="Be brief.",
        messages=[{"role": "user", "content": "What changed?"}])
    assert message.type == "message" and message.role == "assistant"
    assert message.content[0].type == "text"
    assert message.content[0].text == "Wrote n.txt.\nNothing else changed."
    assert message.stop_reason == "end_turn"
    assert (message.usage.input_tokens, message.usage.output_tokens) == (451, 9)
    assert message.model == "gpt-5.3-codex-spark"           # the model that served it
    assert upstream.requests[0]["body"]["messages"][0] == {"role": "system", "content": "Be brief."}
    assert support.kinds(ledger) == ["endpoint_call"]


def test_messages_stream(served):
    url, _upstream, ledger = served([support.stream_answer(stream_bytes("openai", "turn2"))])
    with _client(url).messages.stream(
            model="claude-sonnet-5", max_tokens=64,
            messages=[{"role": "user", "content": "What changed?"}]) as stream:
        pieces = list(stream.text_stream)
        final = stream.get_final_message()
    assert pieces == ["Wrote n.t", "xt.\nNothi", "ng else c", "hanged."]     # as the upstream sent
    assert final.content[0].text == "Wrote n.txt.\nNothing else changed."
    assert final.stop_reason == "end_turn"
    assert (final.usage.input_tokens, final.usage.output_tokens) == (451, 9)
    assert support.kinds(ledger) == ["endpoint_call"]


def test_streamed_tool_call_is_assembled_by_the_sdk(served):
    url, _upstream, _ledger = served([support.stream_answer(stream_bytes("openai", "tool_call"))])
    with _client(url).messages.stream(
            model="claude-sonnet-5", max_tokens=64, tools=[TOOL],
            messages=[{"role": "user", "content": "write a note"}]) as stream:
        final = stream.get_final_message()
    call = final.content[1]
    assert final.stop_reason == "tool_use" and call.type == "tool_use"
    assert (call.name, call.input) == ("write_file", {"path": "n.txt", "content": "hi"})


def test_tool_round_trip(served):
    url, upstream, ledger = served([support.json_answer(plain_object("openai", "tool_call")),
                                    support.json_answer(plain_object("openai", "turn2"))])
    client = _client(url)
    history = [{"role": "user", "content": "write a note"}]
    first = client.messages.create(model="claude-sonnet-5", max_tokens=64, tools=[TOOL],
                                   messages=history)
    call = next(block for block in first.content if block.type == "tool_use")
    assert first.stop_reason == "tool_use"
    assert (call.id, call.name, call.input) == (
        "call_fixtureWrite01", "write_file", {"path": "n.txt", "content": "hi"})
    history += [{"role": "assistant", "content": [block.model_dump() for block in first.content]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call.id,
                                              "content": "wrote 2 bytes"}]}]
    second = client.messages.create(model="claude-sonnet-5", max_tokens=64, tools=[TOOL],
                                    messages=history)
    assert second.content[0].text == "Wrote n.txt.\nNothing else changed."
    sent = upstream.requests[1]["body"]["messages"]
    assert sent[1]["tool_calls"][0]["id"] == "call_fixtureWrite01"
    assert sent[2] == {"role": "tool", "tool_call_id": "call_fixtureWrite01",
                       "content": "wrote 2 bytes"}
    assert support.kinds(ledger) == ["endpoint_call", "endpoint_call"]
    assert ledger.verify()


def test_errors_map_to_the_sdk_typed_exceptions(served):
    limited = support.json_answer(support.load("upstream/openai_rate_limited.json"), 429)
    url, upstream, ledger = served([limited])
    client = _client(url)
    with pytest.raises(anthropic.RateLimitError) as limit:
        client.messages.create(model="claude-sonnet-5", max_tokens=64,
                               messages=[{"role": "user", "content": "What changed?"}])
    assert limit.value.status_code == 429
    assert limit.value.body["error"]["type"] == "rate_limit_error"
    with pytest.raises(anthropic.BadRequestError) as orphan:
        client.messages.create(**support.load("requests/orphan_result.json"))
    assert orphan.value.body["error"]["type"] == "invalid_request_error"
    with pytest.raises(anthropic.AuthenticationError):
        _client(url, api_key="wrong-test-token").messages.create(
            model="claude-sonnet-5", max_tokens=64, messages=[{"role": "user", "content": "hi"}])
    assert len(upstream.requests) == 1                      # only the rate-limited call went out
    assert support.kinds(ledger) == ["endpoint_call_failed"]


def test_stream_cut_mid_event_raises_in_the_sdk(served):
    url, _upstream, ledger = served([support.stream_answer(support.raw("upstream/openai_cut.sse"))])
    with pytest.raises(anthropic.APIError) as broken:
        with _client(url).messages.stream(
                model="claude-sonnet-5", max_tokens=64,
                messages=[{"role": "user", "content": "What changed?"}]) as stream:
            list(stream.text_stream)
    assert "stream" in str(broken.value).lower()
    assert support.kinds(ledger) == ["endpoint_call_failed"]
