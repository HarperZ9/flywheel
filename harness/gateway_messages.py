"""gateway_messages.py -- the gateway answers POST /v1/messages itself.

`handle` takes a Messages request body and returns a `Response`: a Message
object, or an event stream in the documented order. `count_tokens` answers
POST /v1/messages/count_tokens.

Two paths, chosen by the upstream:

  same format   an Anthropic upstream gets the client's body with only the
                model replaced, plus the client's `anthropic-version` and
                `anthropic-beta` headers. The reply, or each stream event,
                goes back as the upstream sent it.
  translated    any other upstream gets the turn in its own shape
                (gateway_turn_wire), and the reply is written as a Message.

Either way the reply is read into one neutral `Reply`, the ledger gets one
entry, and the receipt rides as `x_receipt`: a field on a plain body, and a
field on the `message_stop` event of a stream. The gateway's own credential
for the upstream is used; the client's gateway token is never sent upstream.

Token counting is forwarded to an Anthropic upstream. For any other upstream
the answer is 404 `not_found_error`: no count is made up, and Claude Code
falls back to its own estimate when the endpoint is missing
(https://code.claude.com/docs/en/llm-gateway-protocol.md, read 2026-11-13).
"""
from __future__ import annotations

import json
import logging
import uuid

from . import gateway_messages_wire as wire, gateway_turn as _turn

_LOG = logging.getLogger(__name__)
_FORWARDED = ("anthropic-version", "anthropic-beta")


def _passed(headers) -> dict:
    """The client headers an Anthropic upstream must see unchanged."""
    lowered = {str(k).lower(): v for k, v in dict(headers or {}).items()}
    return {name: lowered[name] for name in _FORWARDED if lowered.get(name)}


def _refused(refused: _turn.TurnRefused, request_id: str) -> _turn.Response:
    status = 404 if refused.kind == "not_found" else 400
    _LOG.info("gateway messages request refused (%s): %s", status, refused)
    return _turn.Response(status, wire.error(status, str(refused), request_id),
                          headers={"request-id": request_id})


def _failed(failed: _turn.UpstreamFailed, same: bool, request_id: str) -> _turn.Response:
    """An upstream failure. An Anthropic upstream's own error body is kept."""
    body = failed.body if same and isinstance(failed.body, dict) else None
    if not (body and body.get("type") == "error" and isinstance(body.get("error"), dict)):
        body = wire.error(failed.status, str(failed), request_id)
    return _turn.Response(failed.status, body,
                          headers={"request-id": request_id, **failed.headers})


def _stream_error(failed: _turn.UpstreamFailed) -> bytes:
    return wire.sse("error", wire.error(failed.status, str(failed)))


def _verbatim(turn, stream):
    """An Anthropic upstream's events as sent; `message_stop` gains the receipt."""
    said = False                            # the upstream sent its own error event
    try:
        for _piece, raw, data in stream:
            kind = data.get("type") if isinstance(data, dict) else ""
            if kind == "message_stop":
                continue                    # held back: it goes last, with the receipt
            said = said or kind == "error"
            yield raw
    except _turn.UpstreamFailed as failed:
        if not said:
            yield _stream_error(failed)
        return
    finally:
        stream.close()
    reply = stream.reply
    yield wire.sse("message_stop", {"type": "message_stop", **wire.flags(reply),
                                    "x_receipt": _turn.receipt(turn, reply)})


def _block(index: int, start: dict, delta: dict):
    yield wire.sse("content_block_start", {"type": "content_block_start", "index": index,
                                           "content_block": start})
    yield wire.sse("content_block_delta", {"type": "content_block_delta", "index": index,
                                           "delta": delta})
    yield wire.sse("content_block_stop", {"type": "content_block_stop", "index": index})


def _closing(turn, reply, shown: str):
    """The events after the upstream finished: late text, tool calls, the end."""
    index = 1 if shown else 0
    late = reply.text[len(shown):] if reply.text.startswith(shown) else ""
    if shown:
        if late:
            yield wire.sse("content_block_delta", {
                "type": "content_block_delta", "index": 0,
                "delta": {"type": "text_delta", "text": late}})
        yield wire.sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    elif reply.text:
        yield from _block(0, {"type": "text", "text": ""},
                          {"type": "text_delta", "text": reply.text})
        index = 1
    for call in reply.calls:
        yield from _block(index, {"type": "tool_use", "id": call["id"], "name": call["name"],
                                  "input": {}},
                          {"type": "input_json_delta",
                           "partial_json": json.dumps(call["arguments"])})
        index += 1
    yield wire.sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": wire.stop_reason(reply), "stop_sequence": None},
        "usage": wire.usage(reply), **wire.flags(reply)})
    yield wire.sse("message_stop", {"type": "message_stop",
                                    "x_receipt": _turn.receipt(turn, reply)})


def _translated(turn, stream, model: str, message_id: str):
    """Another upstream's stream, written as Messages events."""
    yield wire.sse("message_start", {"type": "message_start", "message": {
        "id": message_id, "type": "message", "role": "assistant", "model": model,
        "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0}}})
    shown = ""
    try:
        for piece, _raw, _data in stream:
            if not piece:
                continue
            if not shown:
                yield wire.sse("content_block_start", {
                    "type": "content_block_start", "index": 0,
                    "content_block": {"type": "text", "text": ""}})
            shown += piece
            yield wire.sse("content_block_delta", {
                "type": "content_block_delta", "index": 0,
                "delta": {"type": "text_delta", "text": piece}})
    except _turn.UpstreamFailed as failed:
        yield _stream_error(failed)
        return
    finally:
        stream.close()
    yield from _closing(turn, stream.reply, shown)


def _uncarried(turn, upstream) -> None:
    if turn.uncarried:
        raise _turn.TurnRefused("invalid", (
            f"content of type {turn.uncarried[0]!r} cannot be carried to the "
            f"{upstream.name!r} endpoint, which does not speak the Messages format; "
            "send it to an Anthropic endpoint or leave it out"))


def handle(body, headers, ledger, environ=None, caller=None) -> _turn.Response:
    """Answer one POST /v1/messages request. `caller` is who the call is charged to."""
    from . import gateway_turn_call as call
    request_id, same = f"req_fw_{uuid.uuid4().hex[:24]}", False
    message_id = f"msg_fw_{uuid.uuid4().hex[:24]}"
    try:
        turn = wire.parse(body)
        turn.caller = caller
        upstream = _turn.resolve_upstream(turn.model, environ)
        same, model = upstream.dialect == "anthropic", upstream.backend.model
        payload = extra = None
        if same:
            payload, extra = {**body, "model": model}, _passed(headers)
        else:
            _uncarried(turn, upstream)
        if turn.stream:
            stream = call.stream(turn, upstream, ledger, payload, extra)
            chunks = (_verbatim(turn, stream) if same
                      else _translated(turn, stream, model, message_id))
            return _turn.Response(200, chunks=chunks, headers={"request-id": request_id})
        reply = call.complete(turn, upstream, ledger, payload, extra)
    except _turn.TurnRefused as refused:
        return _refused(refused, request_id)
    except _turn.UpstreamFailed as failed:
        return _failed(failed, same, request_id)
    receipt = _turn.receipt(turn, reply)
    answer = ({**reply.raw, **wire.flags(reply), "x_receipt": receipt} if same
              else wire.message(reply, model, message_id, receipt))
    return _turn.Response(200, answer, headers={
        "request-id": request_id, "x-receipt-id": receipt["receipt_id"]})


def count_tokens(body, headers, ledger=None, environ=None) -> _turn.Response:
    """Answer one POST /v1/messages/count_tokens request. No ledger entry."""
    from . import gateway_turn_call as call, gateway_turn_wire as write
    request_id = f"req_fw_{uuid.uuid4().hex[:24]}"
    out = {"request-id": request_id}
    try:
        model = body.get("model") if isinstance(body, dict) else None
        if not isinstance(model, str) or not model.strip():
            raise _turn.TurnRefused("invalid", "model: field required")
        upstream = _turn.resolve_upstream(model, environ)
        if upstream.dialect != "anthropic":
            return _turn.Response(404, wire.error(404, (
                f"token counting is not available through the {upstream.name!r} endpoint; "
                "only an Anthropic upstream counts tokens, and no estimate is returned"),
                request_id), headers=out)
        _url, base = write.endpoint(upstream)
        url = f"{upstream.backend.base_url}/v1/messages/count_tokens"
        counted = call.forward(upstream, url, {**base, **_passed(headers)},
                               {**body, "model": upstream.backend.model})
    except _turn.TurnRefused as refused:
        return _refused(refused, request_id)
    except _turn.UpstreamFailed as failed:
        _LOG.warning("gateway token count failed (%s)", failed.reason)
        return _failed(failed, True, request_id)
    return _turn.Response(200, counted, headers=out)
