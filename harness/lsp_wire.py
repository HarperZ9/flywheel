"""lsp_wire.py -- Language Server Protocol framing, written from the spec.

LSP is JSON-RPC 2.0 carried over a stream of length-prefixed messages. A header
block in ASCII, a blank line, then exactly that many bytes of UTF-8 JSON. The
messages themselves are plain JSON-RPC and live in harness/jsonrpc.py; this
module is the delimiting contract, so the rules can be tested without starting a
language server.

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

CONTENT_LENGTH = "content-length"
CONTENT_TYPE = "content-type"
DEFAULT_CONTENT_TYPE = "application/vscode-jsonrpc; charset=utf-8"

# A ceiling on one message, so a server that reports a length it will never send
# fails here with a name instead of blocking the reader thread forever. Well
# above any real document: the largest thing that crosses is a didOpen carrying
# a whole file, and 64 MiB of JSON-escaped source is not a file anyone edits.
MAX_CONTENT_LENGTH = 64 * 1024 * 1024

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


def encode(message: dict) -> bytes:
    """Serialize one message with the header block that delimits it.

    The length counts bytes and not characters. Getting that wrong is the
    classic LSP bug, and it only shows up once a message carries a character
    outside ASCII, so the length is taken from the encoded body and never from
    the string.
    """
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


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


def read_headers(stream: BinaryIO) -> dict[str, str] | None:
    """Read one header block. None once the stream has ended cleanly.

    Field names are lowercased on the way in. The specification writes
    Content-Length with that capitalization and every server sends it that way,
    but a case-sensitive reader would fail on a legal variation for no reason.
    """
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            if headers:
                raise WireError("the stream ended inside a header block")
            return None
        if line in (b"\r\n", b"\n"):
            return headers
        try:
            text = line.decode("ascii")
        except UnicodeDecodeError as exc:
            raise WireError(f"a header is ASCII: {exc}") from exc
        name, separator, value = text.partition(":")
        if not separator:
            raise WireError(f"a header is name: value, got {text.strip()!r}")
        headers[name.strip().lower()] = value.strip()


def content_length(headers: dict[str, str]) -> int:
    """The declared body length, or say which rule the header block broke."""
    raw = headers.get(CONTENT_LENGTH)
    if raw is None:
        raise WireError("a message carries a Content-Length header")
    try:
        length = int(raw)
    except ValueError as exc:
        raise WireError(f"Content-Length is an integer, got {raw!r}") from exc
    if length < 0:
        raise WireError(f"Content-Length is not negative, got {length}")
    if length > MAX_CONTENT_LENGTH:
        raise WireError(f"Content-Length {length} is over the "
                        f"{MAX_CONTENT_LENGTH} byte ceiling")
    _check_charset(headers.get(CONTENT_TYPE))
    return length


def _check_charset(content_type: str | None) -> None:
    """UTF-8 or nothing. utf8 is the deprecated spelling and is still accepted.

    A server that declares another charset is not one this client can read, and
    guessing would put mojibake into a chain that claims to hold what crossed.
    """
    if not content_type:
        return
    for part in content_type.split(";")[1:]:
        name, separator, value = part.partition("=")
        if separator and name.strip().lower() == "charset":
            charset = value.strip().strip('"').lower()
            if charset not in ("utf-8", "utf8"):
                raise WireError(f"the body is UTF-8, not {charset!r}")


def read_body(stream: BinaryIO, length: int) -> bytes:
    """Read exactly `length` bytes, or say the message was cut short.

    One read is not enough: a pipe hands back what has arrived rather than what
    was asked for, and the short read is where a client that works on one
    machine starts dropping messages on a slower one.
    """
    chunks: list[bytes] = []
    remaining = length
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise WireError(f"the stream ended {remaining} bytes into a "
                            f"{length} byte message")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


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
