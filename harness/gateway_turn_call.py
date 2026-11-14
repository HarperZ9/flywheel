"""gateway_turn_call.py -- send a neutral turn upstream and read the reply back.

Two calls, one per delivery:

  complete(turn, upstream, ledger)   one request, one `Reply`
  stream(turn, upstream, ledger)     a `Stream`: iterate it for
                                     (text piece, raw event bytes, event data),
                                     then read `.reply`

Both reuse the hosted backends' transports, stream opener, event reader,
assemblers, reply readers and fault reader (endpoints_*), so a reply read here
and a reply read by the coding session come from the same code. Both write the
ledger: `endpoint_call` for a served reply, `endpoint_call_failed` for a call
that failed after the upstream was contacted.

`stream` opens the upstream before it returns, so a refused request raises
`UpstreamFailed` while the interface can still answer with a plain error. A
stream that stops before the provider's end marker raises it mid-iteration.

An interface that speaks the upstream's own format passes `payload` (its
request body with the model replaced) and `headers`; the upstream's events
then reach it byte for byte in the raw field.
"""
from __future__ import annotations

import json
import uuid

from . import gateway_turn as _turn, gateway_turn_wire as _write
from .local_agent import BackendError, MalformedBackendOutput

_STOPS = {
    "openai": {"length": "length", "content_filter": "refusal"},
    "anthropic": {"max_tokens": "length", "refusal": "refusal"},
    "gemini": {"MAX_TOKENS": "length", "SAFETY": "refusal"},
}
_SHAPE = (KeyError, TypeError, AttributeError, IndexError, ValueError)
_RETRY_HEADERS = ("retry-after", "x-should-retry")


def _finish(dialect: str, obj) -> str:
    if dialect == "openai":
        return obj["choices"][0].get("finish_reason") or ""
    if dialect == "gemini":
        return obj["candidates"][0].get("finishReason") or ""
    return obj.get("stop_reason") or ""


def _call(backend, call: dict) -> dict:
    name, arguments = call.get("name"), call.get("arguments")
    if (call.get("arguments_error") or not isinstance(arguments, dict)
            or not isinstance(name, str) or not name):
        raise MalformedBackendOutput(
            f"{backend.name} sent a tool call without a name or with arguments that "
            "are not a JSON object; the reply was refused")
    given = call.get("id")
    return {"id": given if isinstance(given, str) and given else f"toolu_{uuid.uuid4().hex[:24]}",
            "name": name, "arguments": arguments}


def _usage(gen: dict) -> dict:
    record = gen.get("usage") if isinstance(gen.get("usage"), dict) else {}
    counts = record.get("counts") if isinstance(record.get("counts"), dict) else {}
    read = {key: counts.get(key) if type(counts.get(key)) is int else None
            for key in ("input", "output", "cache_read", "cache_write")}
    if (record.get("input_includes_cache_read") and read["input"] is not None
            and read["cache_read"] is not None):
        read["input"] = max(0, read["input"] - read["cache_read"])
    return read


def read(upstream, obj, payload: dict):
    """An upstream response object as a `Reply`. Raises BackendError on a bad one."""
    from . import endpoints_stream as _stream, endpoints_tools_wire as _wire
    from .endpoints_tools import ToolResultClaimed
    backend, dialect = upstream.backend, upstream.dialect
    gen = _stream.DIALECTS[dialect].reply(backend, 200, obj, payload, 0)
    try:
        found, _raw, claimed, _needs_id = _wire._IN[dialect](obj, gen)
        finish = _finish(dialect, obj)
    except _SHAPE as exc:
        raise MalformedBackendOutput(
            f"{backend.name} reply is not in the documented shape "
            f"({type(exc).__name__})") from exc
    if claimed:
        raise ToolResultClaimed(
            f"{backend.name} reply carries a tool result the client did not produce; "
            "the reply was refused and nothing from it was served")
    calls = [_call(backend, call) for call in found]
    stop = _STOPS[dialect].get(finish) or ("tool" if calls else "end")
    served = (gen.get("usage") or {}).get("served_model") or ""
    return _turn.Reply(text=gen["text"], calls=calls, stop_reason=stop, usage=_usage(gen),
                       model_ref=gen["model_ref"], served_model=str(served), raw=obj)


def failure(exc: BaseException) -> "_turn.UpstreamFailed":
    """A backend error as the gateway reports it: a reason code and a status."""
    from .endpoints_stream import StreamIncomplete
    from .endpoints_tools import ToolResultClaimed
    status = getattr(exc, "status", None)
    refused = isinstance(status, int) and 400 <= status < 600
    if isinstance(exc, ToolResultClaimed):
        reason = "tool_result_claimed"
    elif isinstance(exc, StreamIncomplete):
        reason = "stream_incomplete"
    elif isinstance(exc, MalformedBackendOutput):
        reason = "malformed_reply"
    else:
        reason = f"upstream_status_{status}" if refused else "upstream_error"
    return _turn.UpstreamFailed(str(exc), status=status if refused else 502, reason=reason,
                                body=getattr(exc, "body", None),
                                headers=getattr(exc, "retry_headers", None))


def _refusal(backend, status, obj, kind: str) -> BackendError:
    """The error for a non-200 answer, with the retry headers it arrived with."""
    from . import endpoints_http
    last = getattr(endpoints_http._FAULT, "last", None)
    headers = last[1] if last is not None and last[0] is obj else {}
    error = endpoints_http._response_error(backend.name, status, obj, kind=kind)
    error.retry_headers = {str(k).lower(): str(v) for k, v in headers.items()
                           if str(k).lower() in _RETRY_HEADERS}
    return error


def _prepared(turn, upstream, payload, headers) -> tuple:
    if payload is None:
        return _write.request(turn, upstream)
    url, base = _write.endpoint(upstream, turn.max_tokens)
    return url, {**base, **(headers or {})}, payload


def _post(upstream, url: str, headers: dict, payload: dict) -> tuple:
    from .endpoints import _drop_temperature
    from .endpoints_http import _guard
    backend = upstream.backend

    def send():
        return _guard(backend.transport, "POST", url, headers,
                      json.dumps(payload).encode(), backend.timeout, backend.name)
    status, obj = send()
    if upstream.dialect == "anthropic" and _drop_temperature(backend.model, status, obj, payload):
        status, obj = send()
    return status, obj


def complete(turn, upstream, ledger, payload=None, headers=None):
    """Send one request and return the `Reply`, with its ledger entry written."""
    url, headers, payload = _prepared(turn, upstream, payload, headers)
    try:
        status, obj = _post(upstream, url, headers, payload)
        if status != 200:
            raise _refusal(upstream.backend, status, obj, upstream.dialect)
        reply = read(upstream, obj, payload)
    except BackendError as exc:
        failed = failure(exc)
        _turn.record_failed(ledger, upstream, turn, failed.reason, exc)
        raise failed from exc
    _turn.record(ledger, upstream, turn, reply)
    return reply


def forward(upstream, url: str, headers: dict, payload: dict) -> dict:
    """POST one JSON body upstream outside a turn (token counting). No ledger entry."""
    try:
        status, obj = _post(upstream, url, headers, payload)
        if status != 200:
            raise _refusal(upstream.backend, status, obj, upstream.dialect)
    except BackendError as exc:
        raise failure(exc) from exc
    return obj


class Stream:
    """An opened upstream stream. Iterate, then read `.reply`."""

    def __init__(self, events):
        self._events, self.reply = events, None

    def __iter__(self):
        self.reply = yield from self._events

    def close(self) -> None:
        self._events.close()


def _open(upstream, url: str, headers: dict, payload: dict) -> tuple:
    from . import endpoints_stream as _stream
    spec, backend = _stream.DIALECTS[upstream.dialect], upstream.backend
    url, body = spec.prepare(backend, url, payload)
    headers = {**headers, "Accept": "text/event-stream"}
    status, lines = _stream._open(backend, url, headers, body)
    if status != 200 and spec.retry(backend, status, lines, body):
        status, lines = _stream._open(backend, url, headers, body)
    if status != 200:
        raise _refusal(backend, status, lines, spec.kind or backend.name)
    return lines, body


def _events(backend, assembler, lines):
    """Yield (text piece, raw bytes, data) for each event the upstream sends."""
    from . import endpoints_stream as _stream
    from .endpoints_sse import events
    from .provider_fault_boundary import redacted_text
    seen = []

    def tee():
        for raw in lines:
            seen.append(raw if isinstance(raw, bytes) else str(raw).encode("utf-8"))
            yield raw
    try:
        for event, data in events(tee()):
            raw, seen[:] = b"".join(seen), []
            yield assembler.feed(event, data), raw, data
            if assembler.error is not None:
                return
    except _stream._BROKEN as exc:
        why = redacted_text(f"{type(exc).__name__}: {exc}")
        raise _stream._stopped(backend, assembler, why) from exc
    finally:
        close = getattr(lines, "close", None)
        if callable(close):
            close()


def _relay(turn, upstream, ledger, lines, body):
    from . import endpoints_stream as _stream
    spec, backend = _stream.DIALECTS[upstream.dialect], upstream.backend
    assembler = spec.assembler()
    try:
        yield from _events(backend, assembler, lines)
        reply = read(upstream, _stream._finished(backend, spec, assembler), body)
    except BackendError as exc:
        failed = failure(exc)
        _turn.record_failed(ledger, upstream, turn, failed.reason, exc)
        raise failed from exc
    except GeneratorExit:
        _turn.record_failed(ledger, upstream, turn, "client_disconnected",
                            "the client closed the stream before the reply was complete")
        raise
    _turn.record(ledger, upstream, turn, reply)
    return reply


def stream(turn, upstream, ledger, payload=None, headers=None) -> Stream:
    """Open the upstream stream now; return a `Stream` to iterate."""
    url, headers, payload = _prepared(turn, upstream, payload, headers)
    try:
        lines, body = _open(upstream, url, headers, payload)
    except BackendError as exc:
        failed = failure(exc)
        _turn.record_failed(ledger, upstream, turn, failed.reason, exc)
        raise failed from exc
    return Stream(_relay(turn, upstream, ledger, lines, body))
