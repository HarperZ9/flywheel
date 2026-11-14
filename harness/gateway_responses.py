"""gateway_responses.py -- the gateway answers POST /v1/responses itself.

`handle` takes an OpenAI Responses request body and returns a `Response`: a
Response object, or an event stream in the documented order.

Every upstream is reached through the neutral turn: the request is parsed
(gateway_responses_wire), written in the upstream's own shape
(gateway_turn_wire: OpenAI-compatible chat, Anthropic Messages, Gemini) and the
reply is written back as a Response object (gateway_responses_reply). There is
no verbatim path. No upstream the gateway knows serves /v1/responses itself;
an OpenAI-compatible upstream is called on /v1/chat/completions.

The reply is read into one neutral `Reply`, the ledger gets one entry with
`"interface": "openai-responses"`, and the receipt rides as `x_receipt` on the
Response object: in the plain body, and inside the last event of a stream. The
gateway's own credential for the upstream is used; the client's gateway token
is never sent upstream.

A stream that fails after it began ends with `response.failed`, carrying a
Response object whose `status` is `failed`. It gets no `response.completed`.
"""
from __future__ import annotations

import logging
import uuid

from . import (gateway_responses_reply as write, gateway_responses_wire as wire,
               gateway_turn as _turn)

_LOG = logging.getLogger(__name__)


def _refused(refused: _turn.TurnRefused, headers: dict) -> _turn.Response:
    status = 404 if refused.kind == "not_found" else 400
    _LOG.info("gateway responses request refused (%s): %s", status, refused)
    param = "model" if status == 404 else getattr(refused, "param", None)
    return _turn.Response(status, write.error(status, str(refused), param), headers=headers)


def _failed(failed: _turn.UpstreamFailed, upstream, headers: dict) -> _turn.Response:
    """An upstream failure. An OpenAI-format error body is kept as the upstream sent it."""
    body = failed.body if upstream is not None and upstream.dialect == "openai" else None
    inner = body.get("error") if isinstance(body, dict) else None
    if not (isinstance(inner, dict) and isinstance(inner.get("message"), str)):
        body = write.error(failed.status, str(failed))
    return _turn.Response(failed.status, body, headers={**headers, **failed.headers})


def _closing(turn, reply, ids, model: str, echo: dict, events, shown: str):
    """The events after the upstream finished: late text, calls, the last event."""
    body = write.response(reply, ids, model, echo, _turn.receipt(turn, reply))
    items = body["output"]
    if reply.text:
        item = items[0]
        if not shown:
            yield from events.text_open(item["id"])
        late = reply.text[len(shown):] if reply.text.startswith(shown) else ""
        if late:
            yield events.text_delta(item["id"], late)
        yield from events.text_close(item)
    for index, item in enumerate(items):
        if item["type"] == "function_call":
            yield from events.call(index, item)
    last = "response.completed" if body["status"] == "completed" else "response.incomplete"
    yield events.write(last, response=body)


def _stream(turn, stream, ids, model: str, echo: dict, events):
    """An upstream stream, written as Responses events."""
    opened = write.skeleton(ids, model, echo, "in_progress")
    yield events.write("response.created", response=opened)
    yield events.write("response.in_progress", response=opened)
    item_id, shown = ids.item("msg", 0), ""
    try:
        for piece, _raw, _data in stream:
            if not piece:
                continue
            if not shown:
                yield from events.text_open(item_id)
            shown += piece
            yield events.text_delta(item_id, piece)
    except _turn.UpstreamFailed as failed:
        yield events.write("response.failed",
                           response=write.failed(ids, model, echo, str(failed)))
        return
    finally:
        stream.close()
    yield from _closing(turn, stream.reply, ids, model, echo, events, shown)


def handle(body, headers, ledger, environ=None, caller=None) -> _turn.Response:
    """Answer one POST /v1/responses request. `caller` is who the call is charged to."""
    from . import gateway_turn_call as call
    ids, upstream = write.Ids(uuid.uuid4().hex[:24]), None
    out = {"x-request-id": f"req_fw_{uuid.uuid4().hex[:24]}"}
    try:
        turn, echo = wire.parse(body)
        turn.caller = caller
        upstream = _turn.resolve_upstream(turn.model, environ)
        model = upstream.backend.model
        if turn.stream:
            events = write.Events()
            chunks = _stream(turn, call.stream(turn, upstream, ledger), ids, model, echo,
                             events)
            return _turn.Response(200, chunks=chunks, headers=out, fault=events.fault)
        reply = call.complete(turn, upstream, ledger)
    except _turn.TurnRefused as refused:
        return _refused(refused, out)
    except _turn.UpstreamFailed as failed:
        return _failed(failed, upstream, out)
    receipt = _turn.receipt(turn, reply)
    return _turn.Response(200, write.response(reply, ids, model, echo, receipt),
                          headers={**out, "x-receipt-id": receipt["receipt_id"]})
