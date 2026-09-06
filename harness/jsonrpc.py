"""jsonrpc.py -- JSON-RPC 2.0 messages, with no opinion about framing.

Two protocols in this harness speak JSON-RPC and disagree only about how a
message is delimited on the byte stream. ACP puts one message on a line. LSP
puts a Content-Length header in front of it. What either of them does with a
message once it is parsed is the same work, so that work lives here, and the
disagreement lives in the wire modules that import this one.

Written from the JSON-RPC 2.0 specification rather than from a library, for the
reason harness/acp_wire.py gives: if this file and a real peer disagree about
what a message is, the disagreement should surface as a failure rather than as
two copies of one mistake.

The rules asserted are the ones a peer gets wrong quietly. A notification is a
request with no id, and answering one is a protocol violation rather than a
wasted message. An id is a string or a number. A response carries exactly one
of result or error.
"""
from __future__ import annotations

from dataclasses import dataclass, field

JSONRPC = "2.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

REQUEST = "request"
NOTIFICATION = "notification"
RESPONSE = "response"
FAILURE = "failure"


class WireError(ValueError):
    """A frame that is not a JSON-RPC message. The message names the rule."""


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
    """Name the kind of one message, or say which rule it breaks."""
    if not isinstance(message, dict):
        raise WireError("a JSON-RPC message is a JSON object")
    if message.get("jsonrpc") != JSONRPC:
        raise WireError('a JSON-RPC message carries jsonrpc "2.0"')
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


@dataclass(frozen=True)
class Frame:
    """One decoded unit of stream: messages to act on, faults to send back.

    Faults are carried rather than raised for two reasons. A bad entry inside a
    batch produces its own error response and does not discard the entries
    beside it. And a content fault a peer can recover from (bad JSON inside a
    well-formed envelope) is answered and read past, where a framing fault that
    leaves the stream at an unknown offset is raised and ends the connection.
    """

    messages: tuple[dict, ...] = ()
    faults: tuple[dict, ...] = ()
    batched: bool = False
    kinds: tuple[str, ...] = field(default=(), repr=False)


def parse_error(exc: Exception) -> dict:
    """The single response a frame that is not JSON earns: id null, -32700."""
    return failure(None, PARSE_ERROR, f"Parse error: {exc}")
