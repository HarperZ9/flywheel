"""False-success controls for hosted streaming.

A stream that stops before the provider's end marker has no reply. The
controls here cut recorded streams at chosen points and require that the turn
fails, that no tool call from the cut stream runs, and that nothing from it is
recorded. They also pin the opposite case, so the controls cannot pass by
refusing everything: a stream that never began is asked again without
streaming, and that turn succeeds.
"""
import pytest

from harness import endpoints_stream
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.code_session.streaming import _generation, streamed_send
from harness.endpoints_stream import StreamIncomplete
from harness.local_agent import BackendError, MalformedBackendOutput
from tests.hosted_stream_fixtures import (CALL, MESSAGES, NATIVE, PROVIDERS, backend, drain,
                                          plain_object, stream_bytes)

# Where each provider's native tool call is cut. OpenAI and Anthropic send the
# arguments in pieces, so the cut leaves a call with a name and half its
# arguments. Gemini sends a call whole, so the cut ends the stream after the
# last text chunk, before the call and the end marker arrive.
MID_TOOL = {"openai": b'"arguments":"{\\"path\\":',
            "anthropic": b'"partial_json":"{\\"path\\":',
            "gemini": b'"text":"he note."'}


def _cut(data: bytes, marker: bytes) -> bytes:
    assert marker in data
    return data[:data.index(marker) + len(marker)]


def _cut_event(data: bytes, marker: bytes) -> bytes:
    """Everything up to the end of the event that holds `marker`."""
    return data[:data.index(b"\n\n", data.index(marker)) + 2]


def _session(tmp_path, made):
    return new_session(build_agent([made]), str(tmp_path), mode="auto",
                       runner=lambda cmd, root: (True, "[exit 0]"))


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_stream_that_drops_a_native_tool_call_has_no_reply(provider):
    whole = stream_bytes(provider, NATIVE[provider])
    cut = _cut_event if provider == "gemini" else _cut
    made = backend(provider, streams=[cut(whole, MID_TOOL[provider])])
    with pytest.raises(StreamIncomplete) as caught:
        drain(made.chat_streamed(MESSAGES, **CALL))
    assert "no tool call from it ran" in str(caught.value)
    control = backend(provider, streams=[whole])        # the uncut stream is accepted
    _pieces, gen = drain(control.chat_streamed(MESSAGES, **CALL))
    assert gen["text"] == "I will write the note."


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_turn_whose_stream_drops_mid_tool_call_fails_and_runs_nothing(tmp_path, provider):
    cut = _cut_event(stream_bytes(provider, "turn1"), b"TOOL")
    made = backend(provider, streams=[cut], plain=[plain_object(provider, "turn1")])
    session = _session(tmp_path, made)
    shown, ends = [], []
    with streamed_send(session.agent, shown.append, ends.append):
        with pytest.raises(BackendError) as caught:
            session.turn("write a note")
    assert "stopped before the reply was complete" in str(caught.value)
    assert "".join(shown).endswith("TOOL") or "TOOL " in "".join(shown)   # partly on screen
    assert ends == [None]                                # and the display was told
    assert not (tmp_path / "n.txt").exists()             # the call never ran
    kinds = [e.kind for e in session.ledger.entries]
    assert "assistant" not in kinds and "tool_call" not in kinds
    assert made.transport.requests == []                 # not asked again: no second charge
    assert session.ledger.verify()


def test_the_cut_point_matters_only_before_the_end_marker():
    """Control on the control: the same file, cut after its end marker, is a reply."""
    whole = stream_bytes("anthropic", "turn1")
    after_end = _cut(whole, b'"type":"message_stop"}')
    _pieces, gen = drain(backend("anthropic", streams=[after_end]).chat_streamed(MESSAGES, **CALL))
    assert gen["text"].startswith("I will write the note.")
    before_end = whole[:whole.index(b"event: message_stop")]
    with pytest.raises(StreamIncomplete):
        drain(backend("anthropic", streams=[before_end]).chat_streamed(MESSAGES, **CALL))
    open_block = whole.replace(b'event: content_block_stop\ndata: {"type":"content_block_stop",'
                               b'"index":0}\n\n', b"")
    with pytest.raises(StreamIncomplete):
        drain(backend("anthropic", streams=[open_block]).chat_streamed(MESSAGES, **CALL))


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_stream_that_never_began_is_asked_again_without_streaming(tmp_path, provider):
    made = backend(provider, streams=[b"", stream_bytes(provider, "turn2")],
                   plain=[plain_object(provider, "turn1")])
    session = _session(tmp_path, made)
    ends = []
    with streamed_send(session.agent, lambda piece: None, ends.append):
        result = session.turn("write a note")
    assert ends[0] is None and result.final == "Wrote n.txt.\nNothing else changed."
    assert len(made.transport.requests) == 1 and (tmp_path / "n.txt").read_text() == "hi"


def test_a_provider_error_event_after_text_cuts_the_reply():
    body = _cut(stream_bytes("anthropic", "turn1"), b'"text":"I will wr"}}\n\n') + (
        b'event: error\ndata: {"type": "error", "error": {"type": "overloaded_error", '
        b'"message": "Overloaded"}}\n\n')
    with pytest.raises(StreamIncomplete) as caught:
        drain(backend("anthropic", streams=[body]).chat_streamed(MESSAGES, **CALL))
    assert "the provider sent an error" in str(caught.value)


def test_a_refused_stream_request_is_an_ordinary_error_with_the_fault_reading():
    refusal = (401, {"error": {"type": "authentication_error", "message": "invalid x-api-key"}})
    with pytest.raises(BackendError) as caught:
        drain(backend("anthropic", streams=[refusal]).chat_streamed(MESSAGES, **CALL))
    assert not isinstance(caught.value, MalformedBackendOutput)
    assert caught.value.status == 401


def test_anthropic_drops_a_refused_temperature_once_and_streams(monkeypatch):
    monkeypatch.setattr("harness.endpoints._NO_TEMPERATURE", set())
    refusal = (400, {"error": {"type": "invalid_request_error",
                               "message": "temperature is deprecated for this model"}})
    made = backend("anthropic", streams=[refusal, stream_bytes("anthropic", "turn2")])
    _pieces, gen = drain(made.chat_streamed(MESSAGES, **CALL))
    first, second = made.stream_transport.requests
    assert "temperature" in first["body"] and "temperature" not in second["body"]
    assert gen["text"] == "Wrote n.txt.\nNothing else changed."


def test_an_openai_compatible_host_that_refuses_stream_options_still_streams(monkeypatch):
    monkeypatch.setattr(endpoints_stream, "_NO_STREAM_OPTIONS", set())
    refusal = (400, {"error": {"message": "Unrecognized request argument: stream_options"}})
    made = backend("openai", streams=[refusal, stream_bytes("openai", "turn2"),
                                      stream_bytes("openai", "turn2")])
    drain(made.chat_streamed(MESSAGES, **CALL))
    drain(made.chat_streamed(MESSAGES, **CALL))
    bodies = [r["body"] for r in made.stream_transport.requests]
    assert ["stream_options" in b for b in bodies] == [True, False, False]   # learned once


def test_text_that_was_shown_must_be_the_text_that_is_returned():
    gen = {"text": "the reply", "model_ref": "anthropic:claude-sonnet-5", "seed": 0}
    assert _generation(None, "the reply", gen, 8, 0.0, 0) is gen
    with pytest.raises(MalformedBackendOutput):
        _generation(None, "something else was shown", gen, 8, 0.0, 0)
    with pytest.raises(MalformedBackendOutput):
        _generation(None, "the reply", {"text": "the reply"}, 8, 0.0, 0)
