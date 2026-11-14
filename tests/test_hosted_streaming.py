"""Hosted backends stream, and a streamed turn records what a plain turn records.

Every test replays a recorded provider stream from fixtures/provider_streams
through the backend's injected stream transport. No test opens a socket to a
provider. The wire-format sources and the date they were read are in
tests/hosted_stream_fixtures.py.
"""
import dataclasses

import pytest

from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.code_session.streaming import streamed_send
from harness.endpoints_assemble import (AnthropicAssembler, GeminiAssembler,
                                        OpenAIAssembler)
from harness.endpoints_sse import DONE, events
from tests.hosted_stream_fixtures import (CALL, MESSAGES, NATIVE, PROVIDERS, TURNS, backend,
                                          drain, plain_object, stream_bytes)

EVERY = [(p, n) for p in PROVIDERS for n in (*TURNS, NATIVE[p])]
ASSEMBLERS = {"openai": OpenAIAssembler, "anthropic": AnthropicAssembler,
              "gemini": GeminiAssembler}


def _without_stream_gate(gen: dict) -> dict:
    """The generation minus the one field that reads the request body.

    `gates` says whether the request asked a stream for its usage block, so it
    differs between a streamed and a plain request by design."""
    return {k: v for k, v in gen.items() if k != "gates"}


@pytest.mark.parametrize("provider, name", EVERY)
def test_a_replayed_stream_returns_what_the_plain_reply_returns(provider, name):
    made = backend(provider, streams=[stream_bytes(provider, name)],
                   plain=[plain_object(provider, name)])
    pieces, streamed = drain(made.chat_streamed(MESSAGES, **CALL))
    plain = made.chat(MESSAGES, **CALL)
    assert "".join(pieces) == streamed["text"] == plain["text"]
    assert len(pieces) > 1                              # delivered in pieces
    assert streamed["token_usage"] == plain["token_usage"]      # the provider's own counts
    assert streamed["usage"] == plain["usage"]          # the verbatim usage record
    assert _without_stream_gate(streamed) == _without_stream_gate(plain)
    if provider != "openai":
        assert streamed == plain


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_native_tool_call_is_assembled_whole(provider):
    assembler = ASSEMBLERS[provider]()
    for event, data in events(stream_bytes(provider, NATIVE[provider]).splitlines(keepends=True)):
        assembler.feed(event, data)
    assert assembler.complete()
    built, sent = assembler.response(), plain_object(provider, NATIVE[provider])
    want = {"path": "n.txt", "content": "hi"}
    if provider == "anthropic":
        assert built == sent and built["content"][1]["input"] == want
    elif provider == "gemini":
        assert built["candidates"][0]["content"]["parts"][-1] == \
            sent["candidates"][0]["content"]["parts"][-1] == \
            {"functionCall": {"name": "write_file", "args": want}}
    else:
        assert built["choices"][0]["message"]["tool_calls"] == \
            sent["choices"][0]["message"]["tool_calls"]
        made = backend(provider, streams=[stream_bytes(provider, NATIVE[provider])])
        _pieces, gen = drain(made.chat_streamed(MESSAGES, **CALL))
        assert gen["tool_calls"] == [{"id": "call_fixtureWrite01", "name": "write_file",
                                      "arguments": want}]


def _session(tmp_path, made):
    tmp_path.mkdir(parents=True, exist_ok=True)
    return new_session(build_agent([made]), str(tmp_path), mode="auto",
                       runner=lambda cmd, root: (True, "[exit 0]"))


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_streamed_turn_writes_the_ledger_a_plain_turn_writes(tmp_path, provider):
    plain_backend = backend(provider, plain=[plain_object(provider, n) for n in TURNS])
    stream_backend = backend(provider, streams=[stream_bytes(provider, n) for n in TURNS])
    plain = _session(tmp_path / "plain", plain_backend)
    streamed = _session(tmp_path / "streamed", stream_backend)
    shown = []
    first = plain.turn("write a note")
    with streamed_send(streamed.agent, shown.append):
        second = streamed.turn("write a note")

    def record(session):
        return [dataclasses.asdict(e) for e in session.ledger.entries
                if e.kind in ("user", "assistant", "tool_call", "tool_result", "approval")]
    assert record(plain) == record(streamed)            # content, meta and receipt ids
    assert [e.kind for e in plain.ledger.entries] == [e.kind for e in streamed.ledger.entries]
    assert plain.ledger.verify() and streamed.ledger.verify()
    assert first.final == second.final == "Wrote n.txt.\nNothing else changed."
    assert first.steps == second.steps == 2
    assert (tmp_path / "plain" / "n.txt").read_text() == "hi"
    assert (tmp_path / "streamed" / "n.txt").read_text() == "hi"
    assert plain.agent.history == streamed.agent.history
    assert plain.usage == streamed.usage and streamed.usage["uncounted_calls"] == 0
    assert "".join(shown).endswith(second.final) and len(shown) > 4
    assert len(stream_backend.stream_transport.requests) == 2
    assert stream_backend.transport.requests == []      # no second, plain request was made
    assert plain_backend.stream_transport.requests == []


def test_each_provider_is_asked_to_stream_in_its_documented_way():
    asked = {}
    for provider in PROVIDERS:
        made = backend(provider, streams=[stream_bytes(provider, "turn2")])
        drain(made.chat_streamed(MESSAGES, **CALL))
        asked[provider] = made.stream_transport.requests[0]
    assert asked["openai"]["body"]["stream"] is True
    assert asked["openai"]["body"]["stream_options"] == {"include_usage": True}
    assert asked["openai"]["url"].endswith("/chat/completions")
    assert asked["anthropic"]["body"]["stream"] is True
    assert asked["anthropic"]["url"].endswith("/v1/messages")
    assert asked["gemini"]["url"].endswith("/models/gemini-2.5-flash:streamGenerateContent?alt=sse")
    assert "stream" not in asked["gemini"]["body"]
    for provider, request in asked.items():
        assert request["headers"]["Accept"] == "text/event-stream"
        assert "test-key" not in request["url"]         # a key never rides the URL


def test_the_plain_request_is_unchanged_by_the_streaming_code():
    for provider in PROVIDERS:
        made = backend(provider, plain=[plain_object(provider, "turn2")])
        made.chat(MESSAGES, **CALL)
        sent = made.transport.requests[0]
        assert "stream" not in sent["body"] and "stream_options" not in sent["body"]
        assert "streamGenerateContent" not in sent["url"]
        assert "Accept" not in sent["headers"]


def test_the_event_reader_follows_the_event_stream_format():
    body = (b": a comment\r\n"
            b"event: first\r\ndata: {\"a\":\r\ndata: 1}\r\n\r\n"
            b"data:{\"b\": 2}\n\n"
            b"event: empty\n\n"
            b"data: [DONE]\n\n"
            b"data: {\"last\": true}")
    assert list(events(body.splitlines(keepends=True))) == [
        ("first", {"a": 1}), ("", {"b": 2}), ("", DONE), ("", {"last": True})]
    with pytest.raises(ValueError):
        list(events([b"data: {not json\n", b"\n"]))
