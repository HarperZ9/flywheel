"""lsp_wire.py -- Language Server Protocol framing, written from the spec.

LSP is JSON-RPC 2.0 carried over a stream of length-prefixed messages. A header
block in ASCII, a blank line, then exactly that many bytes of UTF-8 JSON. The
messages themselves are plain JSON-RPC and live in harness/jsonrpc.py, and the
header block is harness/content_length.py because DAP carries its own messages
the same way. What is left here is what an LSP message is, so the rules can be
tested without starting a language server.

Written from the 3.17 specification rather than from a client library, for the
same reason harness/acp_wire.py is: if this file and a real server disagree
about what a message is, the disagreement should surface as a failure rather
than as two copies of one mistake.

Two differences from ACP are worth naming because they change behaviour rather
than syntax. LSP does not support batching, so an array body is one Invalid
Request and never a batch. And a header this side cannot parse ends the
connection instead of being answered, because after a bad length nobody knows
where the next message starts, and reading on from there would invent messages
the server never sent.
"""
from __future__ import annotations

import json
from typing import BinaryIO

from .content_length import (CONTENT_LENGTH, CONTENT_TYPE, MAX_CONTENT_LENGTH,
                             content_length, encode, read_body, read_headers)
from .jsonrpc import (FAILURE, INTERNAL_ERROR, INVALID_PARAMS, INVALID_REQUEST,
                      JSONRPC, METHOD_NOT_FOUND, NOTIFICATION, PARSE_ERROR,
                      REQUEST, RESPONSE, Frame, WireError, classify, failure,
                      notification, parse_error, request, success)

# The specification version this implementation was written from. 3.18 is still
# under development, so 3.17 is what a server can be held to.
PROTOCOL_VERSION = "3.17"

# The codes LSP adds to the JSON-RPC set. ServerNotInitialized is the one a
# client provokes by accident: any request before `initialize` earns it.
SERVER_NOT_INITIALIZED = -32002
UNKNOWN_ERROR_CODE = -32001
REQUEST_FAILED = -32803
SERVER_CANCELLED = -32802
CONTENT_MODIFIED = -32801
REQUEST_CANCELLED = -32800

DEFAULT_CONTENT_TYPE = "application/vscode-jsonrpc; charset=utf-8"

__all__ = ["CONTENT_LENGTH", "CONTENT_MODIFIED", "CONTENT_TYPE",
           "DEFAULT_CONTENT_TYPE", "FAILURE", "Frame", "INTERNAL_ERROR",
           "INVALID_PARAMS", "INVALID_REQUEST", "JSONRPC",
           "MAX_CONTENT_LENGTH", "METHOD_NOT_FOUND", "NOTIFICATION",
           "PARSE_ERROR", "PROTOCOL_VERSION", "REQUEST", "REQUEST_CANCELLED",
           "REQUEST_FAILED", "RESPONSE", "SERVER_CANCELLED",
           "SERVER_NOT_INITIALIZED", "UNKNOWN_ERROR_CODE", "WireError",
           "LspFraming", "classify", "decode", "encode", "failure",
           "notification", "parse_error", "read_body", "read_headers",
           "request", "success"]


def decode(body: bytes | str) -> Frame:
    """Decode one message body into the frame it carries.

    A body that is not JSON is raised, because -32700 is the answer to that and
    the caller is the one holding the stream. A body that is JSON but not a
    JSON-RPC message comes back as an Invalid Request fault, which is a
    different code for a different mistake.
    """
    try:
        text = body.decode("utf-8") if isinstance(body, bytes) else body
        payload = json.loads(text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise WireError(f"Parse error: {exc}") from exc
    if isinstance(payload, list):
        # LSP has no batching. An array is a well-formed JSON value and not a
        # message, so it earns one Invalid Request and no attempt to unpack it.
        return Frame(faults=(failure(None, INVALID_REQUEST,
                                     "Invalid Request: LSP does not batch"),))
    try:
        kind = classify(payload)
    except WireError as exc:
        return Frame(faults=(failure(_id_of(payload), INVALID_REQUEST,
                                     f"Invalid Request: {exc}"),))
    return Frame(messages=(payload,), kinds=(kind,))


def _id_of(payload: object) -> int | str | None:
    """The id to blame a fault on, when the message is broken enough to have
    lost it. A response with no id at all is answered with a null id."""
    if isinstance(payload, dict) and isinstance(payload.get("id"), (int, str)):
        return payload["id"]
    return None


class LspFraming:
    """The header block, in the shape harness/jsonrpc_peer.py reads."""

    def encode(self, message: dict) -> bytes:
        return encode(message)

    def read(self, stream: BinaryIO) -> Frame | None:
        headers = read_headers(stream)
        if headers is None:
            return None
        body = read_body(stream, content_length(headers))
        try:
            return decode(body)
        except WireError as exc:
            # The length was good, so the stream is still aligned and the next
            # header block is a whole message. Answer and read on.
            return Frame(faults=(parse_error(exc),))
