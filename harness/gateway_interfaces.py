"""gateway_interfaces.py -- the gateway's model interfaces, on the HTTP handler.

`serve(handler, path, ledger)` is what `gateway.py` calls for the paths in
`PATHS`. It reads the request body, hands it to the interface that owns the
path, and writes the `Response` back: a JSON body, or an event stream sent
chunk by chunk as the upstream produces it.

  /v1/messages               Anthropic Messages (gateway_messages)
  /v1/messages/count_tokens  token counting, forwarded to an Anthropic upstream
  /v1/responses              OpenAI Responses (gateway_responses)

These routes need the gateway token or a virtual key (gateway_keys) and
nothing more. They do not use the per-operation grant flow that guards
/v1/chat/completions, and a virtual key opens no other route.
"""
from __future__ import annotations

import json
import logging

_LOG = logging.getLogger(__name__)
PATHS = ("/v1/messages", "/v1/messages/count_tokens", "/v1/responses")


def _head(handler, status: int, content_type: str, headers: dict) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    for name, value in headers.items():
        handler.send_header(name, str(value))
    handler._cors()


def _fault(response, text: str) -> bytes:
    """The stream error event of the interface that made this response."""
    if response.fault is not None:
        return response.fault(text)
    from .gateway_messages_wire import error, sse
    return sse("error", error(500, text))


def _send_stream(handler, response) -> None:
    """Write an event stream. The upstream was opened before this runs, so the
    `finally` covers the header write as well: a client that reset its
    connection before the headers left never starts the chunk generator, and a
    generator that never started runs no `finally` of its own. `response.close`
    closes the upstream stream either way, which records the call."""
    from .provider_fault_boundary import redacted_text
    try:
        _head(handler, 200, "text/event-stream",
              {"Cache-Control": "no-cache", **response.headers})
        handler.close_connection = True     # the stream ends when the socket closes
        handler.end_headers()
        for chunk in response.chunks:
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except OSError as exc:                  # the client went away mid-stream
        _LOG.info("gateway stream closed by the client (%s)", type(exc).__name__)
    except Exception as exc:                # a fault after the headers left
        _LOG.error("gateway stream failed (%s): %s", type(exc).__name__,
                   redacted_text(str(exc)))
        try:
            handler.wfile.write(_fault(response, f"internal error: {type(exc).__name__}"))
        except OSError:
            _LOG.info("gateway stream error event not delivered; the client had gone")
    finally:
        response.chunks.close()
        if response.close is not None:      # the explicit hook: runs when nothing was read
            response.close()


def send(handler, response) -> None:
    """Write a `Response` on the handler."""
    if response.chunks is not None:
        return _send_stream(handler, response)
    data = json.dumps(response.body).encode("utf-8")
    _head(handler, response.status, "application/json",
          {"Content-Length": len(data), **response.headers})
    handler.end_headers()
    handler.wfile.write(data)


def _body(handler):
    """The request body as a JSON object, or None when it is not one."""
    length = handler._content_length()
    if length is None:
        return None
    try:
        body = json.loads(handler.rfile.read(length) or b"null")
    except (ValueError, RecursionError) as exc:     # not JSON, or nested too deep to parse
        _LOG.info("gateway request body refused (%s)", type(exc).__name__)
        return None
    return body if isinstance(body, dict) else None


def serve(handler, path: str, ledger) -> None:
    """Answer one request on a path in PATHS.

    The caller is settled first (gateway_key_gate): the gateway token is the
    owner, a virtual key is a named caller whose allow-list and limits are
    checked here, before either interface sends anything upstream.

    Two refusals come before that. With no ledger to record the call in, the
    answer is 503 (gateway_ledger_gate). A body that stops arriving is answered
    408 (gateway_read_timeout). Neither reaches an upstream."""
    from . import gateway_key_gate as gate
    if ledger is None:
        from .gateway_ledger_gate import refusal as no_ledger
        return send(handler, no_ledger(path))
    try:
        body = _body(handler)
    except TimeoutError:
        from .gateway_read_timeout import timed_out
        return send(handler, timed_out(handler, path))
    caller, refusal = gate.enter(handler, path, body, ledger)
    if refusal is not None:
        return send(handler, refusal)
    try:
        return _answer(handler, path, body, ledger, caller)
    finally:
        gate.leave(caller)              # the key's in-flight slot, held to the stream's end


def _answer(handler, path: str, body, ledger, caller) -> None:
    headers = {str(name).lower(): value for name, value in handler.headers.items()}
    if path == "/v1/responses":
        from . import gateway_responses
        return send(handler, gateway_responses.handle(body, headers, ledger, caller=caller))
    from . import gateway_messages
    from .gateway_messages_wire import error
    from .gateway_turn import Response
    if body is None:
        return send(handler, Response(400, error(400, "request body must be a JSON object")))
    if path.endswith("/count_tokens"):
        return send(handler, gateway_messages.count_tokens(body, headers, ledger))
    return send(handler, gateway_messages.handle(body, headers, ledger, caller=caller))
