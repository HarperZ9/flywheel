"""endpoints_stream.py -- a hosted backend's reply, delivered as it is written.

`run` is what a hosted backend's `chat_streamed` returns: a generator that
yields each piece of text when the provider sends it and, at the end, returns
the same dict `chat` returns for that reply. The request is the one `chat`
builds, with the provider's stream switch added. The events are rebuilt into
the provider's ordinary response object (endpoints_assemble) and read by the
ordinary reader (endpoints_reply), so the text, the model reference, the token
counts and the observation record are the ones a plain call gives.

Three ways a stream can end, and what each one means:

  complete      the provider sent its end marker. The generation is returned.
  never began   the request was refused, the host was unreachable, or the
                body carried no event. Nothing was shown and nothing was
                billed for output, so this is an ordinary BackendError and the
                caller may ask again without streaming.
  cut short     the stream began and then stopped, broke, or reported an
                error before its end marker. This is StreamIncomplete. The
                text that arrived is not a reply and a tool call that was in
                progress never runs. The caller does not ask again on its
                own: on a hosted provider a second request is a second charge.
"""
from __future__ import annotations

import http.client
import json
from dataclasses import dataclass

from . import endpoints_assemble as _assemble, endpoints_reply as _reply
from . import endpoints_tools_wire as _wire
from .endpoints_http import _guard, _response_error
from .endpoints_sse import events, open_stream
from .local_agent import BackendError, MalformedBackendOutput
from .provider_fault_boundary import redacted_text

# What a broken stream raises while it is read: a dropped connection, a
# transfer cut off, an event that is not JSON, an event without the documented
# fields.
_BROKEN = (OSError, http.client.HTTPException, ValueError, KeyError, TypeError,
           AttributeError, IndexError)

# OpenAI-compatible hosts that refused `stream_options`. Learned from the
# provider's own 400, then remembered, so one request pays for the discovery.
_NO_STREAM_OPTIONS: set = set()


class StreamIncomplete(MalformedBackendOutput):
    """A hosted stream began a reply and did not finish it."""


def _prepare_openai(backend, url: str, payload: dict) -> tuple:
    body = {**payload, "stream": True}
    if backend.base_url not in _NO_STREAM_OPTIONS:
        body["stream_options"] = {"include_usage": True}   # else no token counts
    return url, body


def _retry_openai(backend, status: int, obj, body: dict) -> bool:
    from .endpoints import _error_message
    if status != 400 or "stream_options" not in body:
        return False
    if "stream_options" not in _error_message(obj).lower():
        return False
    _NO_STREAM_OPTIONS.add(backend.base_url)
    body.pop("stream_options")
    return True


def _prepare_anthropic(backend, url: str, payload: dict) -> tuple:
    return url, {**payload, "stream": True}


def _retry_anthropic(backend, status: int, obj, body: dict) -> bool:
    from .endpoints import _drop_temperature
    return _drop_temperature(backend.model, status, obj, body)


def _prepare_gemini(backend, url: str, payload: dict) -> tuple:
    return url.replace(":generateContent", ":streamGenerateContent?alt=sse"), dict(payload)


def _no_retry(backend, status: int, obj, body: dict) -> bool:
    return False


@dataclass(frozen=True)
class Dialect:
    prepare: "callable"        # (backend, url, payload) -> (url, stream body)
    retry: "callable"          # (backend, status, error, body) -> ask once more?
    assembler: "callable"      # () -> endpoints_assemble.Assembler
    reply: "callable"          # the endpoints_reply reader for this dialect
    kind: str = ""             # fault-reading kind; "" means the backend's name


DIALECTS = {
    "openai": Dialect(_prepare_openai, _retry_openai, _assemble.OpenAIAssembler,
                      _reply.openai_reply),
    "anthropic": Dialect(_prepare_anthropic, _retry_anthropic, _assemble.AnthropicAssembler,
                         _reply.anthropic_reply, "anthropic"),
    "gemini": Dialect(_prepare_gemini, _no_retry, _assemble.GeminiAssembler,
                      _reply.gemini_reply, "gemini"),
}


def _open(backend, url: str, headers: dict, body: dict) -> tuple:
    opener = getattr(backend, "stream_transport", None) or open_stream
    return _guard(opener, "POST", url, headers, json.dumps(body).encode(),
                  backend.timeout, backend.name)


def _stopped(backend, assembler, why: str) -> BackendError:
    """The error for a stream with no end marker, by whether it had begun."""
    if not assembler.began:
        return BackendError(f"{backend.name} stream carried no reply: {why}")
    return StreamIncomplete(
        f"{backend.name} stream stopped before the reply was complete ({why}); "
        "nothing from it was recorded and no tool call from it ran")


def _read(backend, assembler, lines):
    """Feed every event to the assembler, yielding the text each one adds."""
    try:
        for event, data in events(lines):
            piece = assembler.feed(event, data)
            if piece:
                yield piece
            if assembler.error is not None:
                return
    except _BROKEN as exc:
        why = redacted_text(f"{type(exc).__name__}: {exc}")
        raise _stopped(backend, assembler, why) from exc
    finally:
        close = getattr(lines, "close", None)
        if callable(close):
            close()


def _finished(backend, spec: Dialect, assembler) -> dict:
    """The assembled response of a stream that ended, or the error it earned."""
    if assembler.error is not None:
        fault = _response_error(backend.name, 200, assembler.error,
                                kind=spec.kind or backend.name)
        if assembler.began:
            raise _stopped(backend, assembler, f"the provider sent an error: {fault}")
        raise fault
    if not assembler.complete():
        raise _stopped(backend, assembler, "the stream ended without the provider's end marker")
    return assembler.response()


def run(backend, dialect: str, request: tuple, seed):
    """Yield the reply's text as it arrives; return what `chat` would return.

    `request` is (url, headers, payload) as the backend's `chat` would send it.
    """
    spec = DIALECTS[dialect]
    url, headers, payload = request
    url, body = spec.prepare(backend, url, payload)
    headers = {**headers, "Accept": "text/event-stream"}
    status, lines = _open(backend, url, headers, body)
    if status != 200 and spec.retry(backend, status, lines, body):
        status, lines = _open(backend, url, headers, body)
    if status != 200:
        _wire.refused(backend, status, lines, body)    # remembered: the plain retry is text
        raise _response_error(backend.name, status, lines, kind=spec.kind or backend.name)
    assembler, shown = spec.assembler(), ""
    for piece in _read(backend, assembler, lines):
        shown += piece
        yield piece
    obj = _finished(backend, spec, assembler)
    try:
        gen = _wire.incoming(dialect, backend, obj, spec.reply(backend, status, obj, body, seed))
    except BackendError as exc:
        exc.stream_complete = True      # asking again would repeat the same reply
        raise
    if gen["text"] != shown and gen["text"].startswith(shown):
        yield gen["text"][len(shown):]  # native calls, written as the TOOL lines recorded
    return gen
