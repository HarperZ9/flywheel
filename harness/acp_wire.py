"""acp_wire.py -- Agent Client Protocol framing, written from the specification.

ACP is JSON-RPC 2.0 carried over a newline-delimited UTF-8 byte stream. One
message per line, no embedded newline, and nothing on the stream that is not an
ACP message. This module is the whole of that contract and knows nothing about
sessions, prompts, or subprocesses, so the rules can be tested without starting
an agent.

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

from dataclasses import dataclass, field
import json

# The MAJOR version this implementation speaks. A single integer, incremented
# only for breaking changes; capability negotiation carries everything else.
PROTOCOL_VERSION = 2
# v1 remains deployed. Reading a v1 initialize response is supported so a client
# can tell an old agent apart from a broken one and say so.
SUPPORTED_VERSIONS = (1, 2)

JSONRPC = "2.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# ACP reserves -32000 to -32099. Two are named by the specification.
AUTH_REQUIRED = -32000
REQUEST_CANCELLED = -32800

REQUEST = "request"
NOTIFICATION = "notification"
RESPONSE = "response"
FAILURE = "failure"


class WireError(ValueError):
    """A frame that is not an ACP message. The message names the rule broken."""


def request(request_id: int | str, method: str, params: object = None) -> dict:
    """A call that expects a result or an error back."""
    message = {"jsonrpc": JSONRPC, "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def notification(method: str, params: object = None) -> dict:
    """A one-way message. A peer must never answer one, even inside a batch."""
    message = {"jsonrpc": JSONRPC, "method": method}
    if params is not None:
        message["params"] = params
    return message


def success(request_id: int | str, result: object) -> dict:
    """The answer to one request."""
    return {"jsonrpc": JSONRPC, "id": request_id, "result": result}


def failure(request_id: int | str | None, code: int, message: str,
            data: object = None) -> dict:
    """A refusal to answer one request, or a fault with no request to blame."""
    error: dict = {"code": int(code), "message": str(message)}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC, "id": request_id, "error": error}


def classify(message: object) -> str:
    """Name the kind of one message, or say which rule it breaks.

    The distinction that matters everywhere else: a notification is a request
    with no id, and answering one is a protocol violation rather than a wasted
    message.
    """
    if not isinstance(message, dict):
        raise WireError("an ACP message is a JSON object")
    if message.get("jsonrpc") != JSONRPC:
        raise WireError('an ACP message carries jsonrpc "2.0"')
    has_id = "id" in message
    if "method" in message:
        if not isinstance(message["method"], str) or not message["method"]:
            raise WireError("method is a non-empty string")
        if has_id and not isinstance(message["id"], (int, str)):
            raise WireError("id is a string or a number")
        return REQUEST if has_id else NOTIFICATION
    if not has_id:
        raise WireError("a response carries the id of its request")
    if "error" in message:
        error = message["error"]
        if not isinstance(error, dict) or not isinstance(error.get("code"), int):
            raise WireError("an error carries an integer code")
        return FAILURE
    if "result" in message:
        return RESPONSE
    raise WireError("a response carries exactly one of result or error")


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


@dataclass(frozen=True)
class Frame:
    """One decoded line: the messages to act on, and the faults to send back.

    Faults are carried rather than raised because the specification says a bad
    entry inside a batch produces its own error response and does not discard
    the entries beside it.
    """

    messages: tuple[dict, ...] = ()
    faults: tuple[dict, ...] = ()
    batched: bool = False
    kinds: tuple[str, ...] = field(default=(), repr=False)


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


def parse_error(exc: Exception) -> dict:
    """The single response a line that is not JSON earns: id null, -32700."""
    return failure(None, PARSE_ERROR, f"Parse error: {exc}")
