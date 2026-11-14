"""gateway_interfaces.py -- the gateway's model interfaces, on the HTTP handler.

`serve(handler, path, ledger)` is what `gateway.py` calls for the paths in
`PATHS`. It reads the request body, hands it to the interface that owns the
path, and writes the `Response` back: a JSON body, or an event stream sent
chunk by chunk as the upstream produces it.

  /v1/messages               Anthropic Messages (gateway_messages)
  /v1/messages/count_tokens  token counting, forwarded to an Anthropic upstream
  /v1/responses              OpenAI Responses (gateway_responses)

These routes need the gateway token and nothing more. They do not use the
per-operation grant flow that guards /v1/chat/completions.
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
    from .provider_fault_boundary import redacted_text
    _head(handler, 200, "text/event-stream", {"Cache-Control": "no-cache", **response.headers})
    handler.close_connection = True         # the stream ends when the socket closes
    handler.end_headers()
    try:
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
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def serve(handler, path: str, ledger) -> None:
    """Answer one request on a path in PATHS."""
    if path == "/v1/responses":
        from . import gateway_responses
        sent = {str(name).lower(): value for name, value in handler.headers.items()}
        return send(handler, gateway_responses.handle(_body(handler), sent, ledger))
    from . import gateway_messages
    from .gateway_messages_wire import error
    from .gateway_turn import Response
    body = _body(handler)
    if body is None:
        return send(handler, Response(400, error(400, "request body must be a JSON object")))
    headers = {str(name).lower(): value for name, value in handler.headers.items()}
    answer = (gateway_messages.count_tokens if path.endswith("/count_tokens")
              else gateway_messages.handle)
    return send(handler, answer(body, headers, ledger))
