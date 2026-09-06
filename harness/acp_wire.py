"""acp_wire.py -- Agent Client Protocol framing, written from the specification.

ACP is JSON-RPC 2.0 carried over a newline-delimited UTF-8 byte stream. One
message per line, no embedded newline, and nothing on the stream that is not an
ACP message. The messages themselves are plain JSON-RPC and live in
harness/jsonrpc.py; this module is the delimiting contract and the two constants
ACP adds, and it knows nothing about sessions, prompts, or subprocesses, so the
rules can be tested without starting an agent.

Written from https://agentclientprotocol.com/protocol/v2/transports rather than
from any reference implementation, for the same reason the bulletin smoke client
is written from RFC 9421: if this file and a real agent ever disagree about what
a frame is, the disagreement should surface as a failure rather than as two
copies of the same mistake.

Inbound batch arrays are accepted because the specification permits a peer to
send one. Nothing here emits a batch. The specification says lifecycle messages
should not be batched, and every message this side sends is lifecycle-adjacent,
so the outbound simplification costs nothing and removes a class of ordering
bug.
"""
from __future__ import annotations

import json
from typing import BinaryIO

from .jsonrpc import (FAILURE, INTERNAL_ERROR, INVALID_PARAMS, INVALID_REQUEST,
                      JSONRPC, METHOD_NOT_FOUND, NOTIFICATION, PARSE_ERROR,
                      REQUEST, RESPONSE, Frame, WireError, classify, failure,
                      notification, parse_error, request, success)

# The MAJOR version this implementation speaks. A single integer, incremented
# only for breaking changes; capability negotiation carries everything else.
PROTOCOL_VERSION = 2
# v1 remains deployed. Reading a v1 initialize response is supported so a client
# can tell an old agent apart from a broken one and say so.
SUPPORTED_VERSIONS = (1, 2)

# ACP reserves -32000 to -32099. Two are named by the specification.
AUTH_REQUIRED = -32000
REQUEST_CANCELLED = -32800

__all__ = ["AUTH_REQUIRED", "AcpFraming", "FAILURE", "Frame", "INTERNAL_ERROR",
           "INVALID_PARAMS", "INVALID_REQUEST", "JSONRPC", "METHOD_NOT_FOUND",
           "NOTIFICATION", "PARSE_ERROR", "PROTOCOL_VERSION", "REQUEST",
           "REQUEST_CANCELLED", "RESPONSE", "SUPPORTED_VERSIONS", "WireError",
           "classify", "decode", "encode", "failure", "notification",
           "parse_error", "request", "success"]


def encode(message: dict) -> bytes:
    """Serialize one message as the line that goes on the stream.

    json.dumps escapes every control character, so the embedded-newline rule
    holds by construction. It is asserted anyway: a future change to the
    serializer would otherwise corrupt framing silently for every later message
    rather than failing here.
    """
    line = json.dumps(message, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False)
    if "\n" in line or "\r" in line:
        raise WireError("a frame contains no embedded newline")
    return (line + "\n").encode("utf-8")


def _entry(raw: object) -> tuple[dict | None, dict | None, str]:
    try:
        kind = classify(raw)
    except WireError:
        return None, failure(None, INVALID_REQUEST, "Invalid Request"), ""
    return raw, None, kind  # type: ignore[return-value]


def decode(line: bytes | str) -> Frame:
    """Decode one line into the messages it carries.

    A line that is not JSON at all is a parse error against the whole line, so
    it is raised. Everything after that point is per-entry, because a batch with
    one bad member is still a batch.
    """
    text = line.decode("utf-8") if isinstance(line, bytes) else line
    try:
        payload = json.loads(text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise WireError(f"Parse error: {exc}") from exc
    if isinstance(payload, list):
        if not payload:
            # An empty array gets one Invalid Request, never a response array.
            return Frame(faults=(failure(None, INVALID_REQUEST,
                                         "Invalid Request"),), batched=True)
        entries = [_entry(item) for item in payload]
        return Frame(messages=tuple(m for m, _, _ in entries if m is not None),
                     faults=tuple(f for _, f, _ in entries if f is not None),
                     batched=True,
                     kinds=tuple(k for _, _, k in entries if k))
    return Frame(messages=(payload,), kinds=(classify(payload),))


class AcpFraming:
    """The newline delimiter, in the shape harness/jsonrpc_peer.py reads.

    A line that is not JSON is answered and read past rather than raised. The
    next line is a whole frame either way, so one bad line from an agent does
    not end a session that is otherwise working.
    """

    def encode(self, message: dict) -> bytes:
        return encode(message)

    def read(self, stream: BinaryIO) -> Frame | None:
        for line in iter(stream.readline, b""):
            if not line.strip():
                continue  # a blank line frames nothing; it is not an error
            try:
                return decode(line)
            except WireError as exc:
                return Frame(faults=(parse_error(exc),))
        return None
