"""gateway_responses_reply.py -- the OpenAI Responses format, written.

`response` writes a neutral `Reply` as a Response object. `Events` writes the
stream: it numbers each event with `sequence_number` and emits them in the
documented order. `error` writes the error body and `status_error` picks its
`type` from the HTTP status.

Usage. `input_tokens` is the whole prompt as OpenAI counts it: the neutral
uncached input plus the cache counts. `input_tokens_details.cached_tokens` is
the provider's cache-read count. The format types both detail counts as
integers, so a count the provider did not send is 0 and the body says so in
`x_flywheel`. `output_tokens_details.reasoning_tokens` is always 0: the neutral
reply carries no reasoning count.

Wire format, read 2026-11-14. platform.openai.com refused the fetch (403), so:
  https://github.com/openai/openai-openapi (manual_spec branch, openapi.yaml):
      Response, ResponseUsage, FunctionToolCall, Error, ErrorResponse, the
      createResponse streaming example (event order), ResponseErrorEvent,
      ResponseFailedEvent, ResponseFunctionCallArgumentsDeltaEvent and
      ResponseFunctionCallArgumentsDoneEvent
  openai Python SDK 2.36.0, types/responses (generated from that spec):
      response, response_usage, response_output_message, response_output_text,
      response_function_tool_call, response_error, and one module per stream
      event (`sequence_number`, `logprobs` on the text events, `name` on
      `response.function_call_arguments.done`)
  https://developers.openai.com/api/docs/guides/error-codes
      error `type` strings: invalid_request_error, rate_limit_error,
      service_unavailable_error
"""
from __future__ import annotations

import json
import time

_TYPES = {429: "rate_limit_error", 503: "service_unavailable_error"}
_INCOMPLETE = {"length": "max_output_tokens", "refusal": "content_filter"}


def error(status: int, text: str, param: "str | None" = None,
          code: "str | None" = None) -> dict:
    """The error body: {"error": {"message", "type", "param", "code"}}."""
    kind = _TYPES.get(status) or ("invalid_request_error" if status < 500 else "server_error")
    return {"error": {"message": text, "type": kind, "param": param, "code": code}}


def sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")


def usage(reply) -> dict:
    """The provider's counts under the Responses names."""
    counts = reply.usage
    cached = counts.get("cache_read") or 0
    total_in = (counts.get("input") or 0) + cached + (counts.get("cache_write") or 0)
    out = counts.get("output") or 0
    return {"input_tokens": total_in, "input_tokens_details": {"cached_tokens": cached},
            "output_tokens": out, "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": total_in + out}


def unreported(reply) -> dict:
    """`x_flywheel` flags for counts the provider did not send."""
    flags = {}
    if not reply.usage_reported:
        flags["usage_reported"] = False
    if reply.usage.get("cache_read") is None:
        flags["cached_tokens_reported"] = False
    return {"x_flywheel": flags} if flags else {}


def _status(reply) -> str:
    return "incomplete" if reply.stop_reason in _INCOMPLETE else "completed"


def message_item(item_id: str, text: "str | None", status: str) -> dict:
    """An output message item; `text` None gives the empty item a stream opens with."""
    content = [] if text is None else [{"type": "output_text", "text": text, "annotations": []}]
    return {"id": item_id, "type": "message", "status": status, "role": "assistant",
            "content": content}


def call_item(item_id: str, call: dict, status: str, arguments: "str | None" = None) -> dict:
    sent = json.dumps(call["arguments"]) if arguments is None else arguments
    return {"id": item_id, "type": "function_call", "status": status,
            "call_id": call["id"], "name": call["name"], "arguments": sent}


def output(reply, ids) -> list:
    """The reply as output items: one message when there is text, then the calls."""
    status = _status(reply)
    items = [message_item(ids.item("msg", 0), reply.text, status)] if reply.text else []
    return items + [call_item(ids.item("fc", len(items) + at), call, "completed")
                    for at, call in enumerate(reply.calls)]


class Ids:
    """The ids of one response and its output items."""

    def __init__(self, token: str):
        self.response, self.created = f"resp_fw_{token}", int(time.time())
        self._token = token

    def item(self, prefix: str, index: int) -> str:
        return f"{prefix}_fw_{self._token}_{index}"


def skeleton(ids, model: str, echo: dict, status: str) -> dict:
    """A Response object with no output yet."""
    return {
        "id": ids.response, "object": "response", "created_at": ids.created,
        "status": status, "error": None, "incomplete_details": None,
        "instructions": echo["instructions"], "max_output_tokens": echo["max_output_tokens"],
        "model": model, "output": [], "parallel_tool_calls": echo["parallel_tool_calls"],
        "previous_response_id": None, "store": False, "temperature": echo["temperature"],
        "text": {"format": {"type": "text"}}, "tool_choice": echo["tool_choice"],
        "tools": echo["tools"], "top_p": echo["top_p"], "truncation": "disabled",
        "usage": None, "metadata": echo["metadata"]}


def response(reply, ids, model: str, echo: dict, receipt: dict) -> dict:
    """A `Reply` as a Response object, with the receipt as an extension field."""
    body = skeleton(ids, model, echo, _status(reply))
    reason = _INCOMPLETE.get(reply.stop_reason)
    body.update(output=output(reply, ids), usage=usage(reply),
                incomplete_details={"reason": reason} if reason else None)
    return {**body, **unreported(reply), "x_receipt": receipt}


def failed(ids, model: str, echo: dict, text: str) -> dict:
    """The Response object a `response.failed` event carries."""
    return {**skeleton(ids, model, echo, "failed"),
            "error": {"code": "server_error", "message": text}}


class Events:
    """Stream events for one response, numbered in the order they are written."""

    def __init__(self):
        self.sequence = 0

    def write(self, kind: str, **fields) -> bytes:
        data = {"type": kind, "sequence_number": self.sequence, **fields}
        self.sequence += 1
        return sse(kind, data)

    def fault(self, text: str) -> bytes:
        """The `error` event, for a fault with no Response object at hand."""
        return self.write("error", code="server_error", message=text, param=None)

    def text_open(self, item_id: str):
        yield self.write("response.output_item.added", output_index=0,
                         item=message_item(item_id, None, "in_progress"))
        yield self.write("response.content_part.added", item_id=item_id, output_index=0,
                         content_index=0,
                         part={"type": "output_text", "text": "", "annotations": []})

    def text_delta(self, item_id: str, piece: str) -> bytes:
        return self.write("response.output_text.delta", item_id=item_id, output_index=0,
                          content_index=0, delta=piece, logprobs=[])

    def text_close(self, item: dict):
        at = {"item_id": item["id"], "output_index": 0, "content_index": 0}
        part = item["content"][0]
        yield self.write("response.output_text.done", **at, text=part["text"], logprobs=[])
        yield self.write("response.content_part.done", **at, part=part)
        yield self.write("response.output_item.done", output_index=0, item=item)

    def call(self, index: int, item: dict):
        """A function call, sent whole: the upstream's arguments arrive assembled."""
        at = {"item_id": item["id"], "output_index": index}
        yield self.write("response.output_item.added", output_index=index,
                         item={**item, "status": "in_progress", "arguments": ""})
        yield self.write("response.function_call_arguments.delta", **at,
                         delta=item["arguments"])
        yield self.write("response.function_call_arguments.done", **at, name=item["name"],
                         arguments=item["arguments"])
        yield self.write("response.output_item.done", output_index=index, item=item)
