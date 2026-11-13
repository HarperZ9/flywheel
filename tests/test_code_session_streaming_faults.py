"""Streamed replies that end badly: interrupt, display error, bad reply, counts."""
import pytest

from harness.code_session.backends import build_agent
from harness.code_session.streaming import streamed_send
from tests.test_code_session_streaming import StreamScript, _assistant, _session


class Careful(StreamScript):
    """Records that its stream was closed, and can stop or misbehave on request."""

    def __init__(self, replies, stop=None, ref="script:script-1"):
        super().__init__(replies)
        self.stop, self.ref, self.closed = stop, ref, False

    def chat_stream(self, messages, *, system, max_tokens, temperature, seed):
        try:
            yield "first "
            if self.stop is not None:
                raise self.stop
            yield "second"
            return self.ref
        finally:
            self.closed = True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": "first second", "model_ref": "script:script-1", "seed": seed,
                "token_usage": {"input_tokens": 11, "output_tokens": 2}}


CALL = {"system": "", "max_tokens": 8, "temperature": 0.0, "seed": 1}


def test_an_interrupt_closes_the_stream_and_tells_the_display(tmp_path):
    backend, ends = Careful([], stop=KeyboardInterrupt()), []
    with streamed_send(build_agent([backend]), lambda piece: None, ends.append):
        with pytest.raises(KeyboardInterrupt):
            backend.chat([], **CALL)
    assert ends == [None] and backend.closed


def test_a_display_error_closes_the_stream_too(tmp_path):
    backend, ends = Careful([]), []

    def broken(piece):
        raise RuntimeError("terminal went away")
    with streamed_send(build_agent([backend]), broken, ends.append):
        with pytest.raises(RuntimeError):
            backend.chat([], **CALL)
    assert ends == [None] and backend.closed


def test_a_stream_that_names_no_model_is_refused_once():
    from harness.local_agent import MalformedBackendOutput
    backend, ends = Careful([], ref=""), []
    with streamed_send(build_agent([backend]), lambda piece: None, ends.append):
        with pytest.raises(MalformedBackendOutput):
            backend.chat([], **CALL)
    assert ends == [None] and backend.closed


def test_token_counts_are_not_recorded_for_a_streamed_reply(tmp_path):
    plain = _session(tmp_path, Careful([]))
    plain.turn("hello")
    assert plain.usage["input_tokens"] == 11 and plain.usage["uncounted_calls"] == 0
    streamed = _session(tmp_path, Careful([]))
    with streamed_send(streamed.agent, lambda piece: None):
        result = streamed.turn("hello")
    assert result.final == "first second"            # the same reply either way
    assert streamed.usage["input_tokens"] == 0 and streamed.usage["uncounted_calls"] == 1
    assert _assistant(plain) == _assistant(streamed)
