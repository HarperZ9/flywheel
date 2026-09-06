"""dap_wire.py -- Debug Adapter Protocol messages, written from the spec.

DAP is not JSON-RPC. It borrows the Content-Length header block, which lives in
harness/content_length.py, and then puts its own envelope inside: every message
carries `seq` and `type`, and the three types are `request`, `response` and
`event`. A response is tied to its request by `request_seq` rather than by a
shared `id`, and a failure is a response with `success: false` rather than a
separate error object.

That difference is why this file exists instead of DAP riding on
harness/jsonrpc.py. Mapping one envelope onto the other would put a translation
layer between the wire and the record, and the record is the product here.

Written from microsoft.github.io/debug-adapter-protocol rather than from a
client library, so a disagreement with a real adapter surfaces as a failure
rather than as two copies of one mistake.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import BinaryIO

from .content_length import content_length, encode, read_body, read_headers
from .jsonrpc import WireError

REQUEST = "request"
RESPONSE = "response"
EVENT = "event"

# The requests this client sends. Named here so the session module reads as the
# lifecycle it is rather than as a wall of string literals.
INITIALIZE = "initialize"
LAUNCH = "launch"
ATTACH = "attach"
SET_BREAKPOINTS = "setBreakpoints"
SET_EXCEPTION_BREAKPOINTS = "setExceptionBreakpoints"
CONFIGURATION_DONE = "configurationDone"
THREADS = "threads"
STACK_TRACE = "stackTrace"
SCOPES = "scopes"
VARIABLES = "variables"
EVALUATE = "evaluate"
CONTINUE = "continue"
NEXT = "next"
STEP_IN = "stepIn"
STEP_OUT = "stepOut"
PAUSE = "pause"
TERMINATE = "terminate"
DISCONNECT = "disconnect"

# The events this client acts on. Others are recorded and left alone.
INITIALIZED = "initialized"
STOPPED = "stopped"
CONTINUED = "continued"
TERMINATED = "terminated"
EXITED = "exited"
OUTPUT = "output"

# The two requests an adapter sends back at its client. Both ask the client to
# start something outside the debuggee, which makes them the grant boundary
# rather than an implementation detail. harness/dap_policy.py answers them.
RUN_IN_TERMINAL = "runInTerminal"
START_DEBUGGING = "startDebugging"
REVERSE_REQUESTS = (RUN_IN_TERMINAL, START_DEBUGGING)

__all__ = ["ATTACH", "CONFIGURATION_DONE", "CONTINUE", "CONTINUED",
           "DISCONNECT", "DapFrame", "DapFraming", "EVALUATE", "EVENT",
           "EXITED", "INITIALIZE", "INITIALIZED", "LAUNCH", "NEXT", "OUTPUT",
           "PAUSE", "REQUEST", "RESPONSE", "REVERSE_REQUESTS",
           "RUN_IN_TERMINAL", "SCOPES", "SET_BREAKPOINTS",
           "SET_EXCEPTION_BREAKPOINTS", "STACK_TRACE", "START_DEBUGGING",
           "STEP_IN", "STEP_OUT", "STOPPED", "TERMINATE", "TERMINATED",
           "THREADS", "VARIABLES", "WireError", "classify", "decode", "encode",
           "error_response", "event", "request", "response"]


@dataclass(frozen=True)
class DapFrame:
    """One unit read off the stream.

    `malformed` carries the reason a well-delimited body was not a message this
    side could use. It is a separate slot rather than an exception because the
    length was good, so the stream is still aligned and the next header block is
    a whole message. Dropping the connection there would lose work over one bad
    message the peer may never repeat.
    """

    message: dict | None = None
    kind: str = ""
    malformed: str = ""


def request(seq: int, command: str, arguments: object = None) -> dict:
    """One request. `arguments` is omitted rather than sent as null.

    Some adapters validate their arguments schema strictly, and an explicit null
    where the schema says the field is absent is a different value from a
    missing field.
    """
    message: dict = {"seq": int(seq), "type": REQUEST, "command": str(command)}
    if arguments is not None:
        message["arguments"] = arguments
    return message


def response(seq: int, request_seq: int, command: str,
             body: object = None) -> dict:
    """A successful answer to the request that carried `request_seq`."""
    message: dict = {"seq": int(seq), "type": RESPONSE,
                     "request_seq": int(request_seq), "success": True,
                     "command": str(command)}
    if body is not None:
        message["body"] = body
    return message


def error_response(seq: int, request_seq: int, command: str,
                   message_text: str) -> dict:
    """A refusal, in the shape the specification gives an ErrorResponse.

    The prose goes in `message` and not only in `body.error`, because that is
    the field a client is required to be able to show and it is what an adapter
    logs when it does not understand the structured form.
    """
    return {"seq": int(seq), "type": RESPONSE,
            "request_seq": int(request_seq), "success": False,
            "command": str(command), "message": str(message_text),
            "body": {"error": {"id": 0, "format": str(message_text),
                               "showUser": False}}}


def event(seq: int, name: str, body: object = None) -> dict:
    """One event. Events are one-way and are never answered."""
    message: dict = {"seq": int(seq), "type": EVENT, "event": str(name)}
    if body is not None:
        message["body"] = body
    return message


def classify(payload: object) -> str:
    """Which of the three kinds this message is, or say why it is none of them.

    `seq` is required on a request and tolerated as missing on a response or an
    event. This side answers a request by quoting its `seq` back as
    `request_seq`, so a request without one cannot be answered at all. Nothing
    routes on the peer's `seq` in the other two cases: responses are matched on
    `request_seq` and events on their name, so refusing those over a field this
    client never reads would drop usable work.
    """
    if not isinstance(payload, dict):
        raise WireError(f"a message is a JSON object, got {type(payload).__name__}")
    kind = payload.get("type")
    if kind == REQUEST:
        _needs_text(payload, "command")
        if not isinstance(payload.get("seq"), int) or isinstance(payload.get("seq"), bool):
            raise WireError("a request carries an integer seq to answer against")
        return REQUEST
    if kind == RESPONSE:
        _needs_text(payload, "command")
        if not isinstance(payload.get("request_seq"), int) or isinstance(payload.get("request_seq"), bool):
            raise WireError("a response carries the integer seq it answers")
        if not isinstance(payload.get("success"), bool):
            raise WireError("a response says whether it succeeded")
        return RESPONSE
    if kind == EVENT:
        _needs_text(payload, "event")
        return EVENT
    raise WireError(f"type is request, response or event, got {kind!r}")


def _needs_text(payload: dict, field: str) -> None:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise WireError(f"{field} is a non-empty string, got {value!r}")


def decode(body: bytes | str) -> DapFrame:
    """Decode one body into the frame it carries.

    A body that is not JSON at all is still a delimited body, so it comes back
    malformed like any other unusable message. There is no protocol-level answer
    to send: DAP has no parse-error reply, and a response needs a `request_seq`
    that an unreadable body does not have.
    """
    try:
        text = body.decode("utf-8") if isinstance(body, bytes) else body
        payload = json.loads(text)
    except (UnicodeDecodeError, ValueError) as exc:
        return DapFrame(malformed=f"the body is not JSON: {exc}")
    try:
        kind = classify(payload)
    except WireError as exc:
        return DapFrame(malformed=str(exc))
    return DapFrame(message=payload, kind=kind)


class DapFraming:
    """The header block plus the DAP envelope, in one place a peer can hold."""

    def encode(self, message: dict) -> bytes:
        return encode(message)

    def read(self, stream: BinaryIO) -> DapFrame | None:
        headers = read_headers(stream)
        if headers is None:
            return None
        return decode(read_body(stream, content_length(headers)))
