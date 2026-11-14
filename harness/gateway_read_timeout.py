"""gateway_read_timeout.py -- a client may not hold a gateway connection silent.

Without a socket timeout a client can send request headers and then nothing,
for any length of time. Each such connection holds a gateway thread, and a
request that is admitted long after its headers arrived was once checked
against key totals that were out of date (the key row is now read again after
the body; see gateway_key_gate.enter).

`arm` sets a timeout on the socket of each connection the gateway accepts. Every read of
the request line, the headers and the body, and every write of the answer,
must make progress within that many seconds, or the connection is closed:

  - a silent request line or header: `http.server` closes the connection;
  - a silent body on a model interface: the gateway answers 408 and closes
    (gateway_interfaces.serve), and nothing is sent upstream.

The default is 30 seconds. FLYWHEEL_GATEWAY_READ_TIMEOUT sets another number
of seconds; `0` or `off` removes the timeout. The timeout is per socket
operation, not a deadline for the whole request: a client that keeps sending
a few bytes holds its connection for longer. That costs a thread and no
provider spend, because nothing is admitted before the body is whole.
"""
from __future__ import annotations

import logging
import os
import uuid

_LOG = logging.getLogger(__name__)
ENV = "FLYWHEEL_GATEWAY_READ_TIMEOUT"
DEFAULT = 30.0


def seconds(environ=None) -> "float | None":
    """The timeout in seconds, or None when it is switched off."""
    raw = ((os.environ if environ is None else environ).get(ENV) or "").strip().lower()
    if raw in ("0", "off", "none", "no", "false"):
        return None
    try:
        value = float(raw) if raw else DEFAULT
    except ValueError:
        _LOG.warning("%s is not a number of seconds; the default of %s is used", ENV, DEFAULT)
        return DEFAULT
    return value if value > 0 else None


def arm(handler) -> None:
    """Set the timeout on a handler's connection. Called from the gateway
    handler's `setup` (gateway_body_drain.BodyDrainMixin), once per connection."""
    limit = seconds()
    sock = getattr(handler, "connection", None)
    if limit is not None and sock is not None:
        sock.settimeout(limit)


def timed_out(handler, path: str):
    """The 408 `Response` for a request body that stopped arriving."""
    from .gateway_turn import Response
    limit = seconds()
    _LOG.warning("gateway request on %s closed: its body did not arrive within the read "
                 "timeout (%s s)", path, limit)
    handler.close_connection = True
    text = (f"the request body did not arrive within the gateway's read timeout of {limit} "
            f"seconds ({ENV}). Nothing was sent upstream.")
    request_id = f"req_fw_{uuid.uuid4().hex[:24]}"
    if path == "/v1/responses":
        from .gateway_responses_reply import error
        return Response(408, error(408, text, None, "request_timeout"),
                        headers={"x-request-id": request_id, "Connection": "close"})
    from .gateway_messages_wire import error
    return Response(408, error(408, text, request_id),
                    headers={"request-id": request_id, "Connection": "close"})
