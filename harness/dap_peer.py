"""dap_peer.py -- one Debug Adapter Protocol peer over a pair of byte streams.

The same job harness/jsonrpc_peer.py does, for an envelope that is not JSON-RPC.
It is written separately rather than as a dialect of that peer because the two
disagree about the parts a peer is made of: DAP matches a response to its
request by `request_seq` instead of a shared `id`, reports failure by a flag on
the response instead of an error member, and numbers every message on one
counter instead of numbering only requests. A shared peer parameterized over
those three would be a translation layer sitting between the wire and the
record, and the record is what this tree sells.

What is shared is everything below the envelope: the header block
(harness/content_length.py), the launch (harness/child_stdio.py) and the chain
(harness/wire_witness.py).

The observer seam is why this layer exists rather than the calls being inlined.
Every message that crosses in either direction is handed to the observer before
anything acts on it, so a receipt over a debug session is taken at the wire and
not reconstructed afterwards from what the adapter chose to report.

One request is sent without waiting for its answer. `launch` has to be in flight
while configuration is still being sent, so `send` and `await_reply` are
separate calls and `call` is the two of them together.
"""
from __future__ import annotations

import itertools
import threading
from typing import Any, BinaryIO, Callable, Protocol

from .dap_wire import (DapFrame, EVENT, REQUEST, RESPONSE, error_response,
                       request, response)
from .jsonrpc_peer import RECEIVED, SENT, ConnectionClosed

Observer = Callable[[str, dict], None]

__all__ = ["AdapterError", "CommandNotSupported", "ConnectionClosed",
           "DapPeer", "Handler", "Observer", "Pending", "RECEIVED",
           "RejectAll", "SENT"]


class CommandNotSupported(LookupError):
    """This side does not answer the reverse request the adapter sent."""


class AdapterError(RuntimeError):
    """A response with success false. The command and prose are the record.

    Written by hand rather than as a dataclass because an exception carries
    `args` and a traceback, and a frozen dataclass quietly leaves both empty.
    """

    def __init__(self, command: str, message: str, body: Any = None) -> None:
        super().__init__(f"{command} failed: {message or 'no reason given'}")
        self.command = command
        self.message = message
        self.body = body


class Handler(Protocol):
    """What this side answers. Both hooks are optional in behaviour, not shape."""

    def on_request(self, command: str, arguments: dict) -> object:
        """Return the body for one reverse request, or raise CommandNotSupported."""

    def on_event(self, name: str, body: dict) -> None:
        """Act on one event. A raise here fails the connection."""


class RejectAll:
    """The default handler: answers nothing, and drops no event silently."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, dict]] = []

    def on_request(self, command: str, arguments: dict) -> object:
        raise CommandNotSupported(command)

    def on_event(self, name: str, body: dict) -> None:
        self.seen.append((name, body))


class Pending:
    """A request that has been sent and not yet answered."""

    __slots__ = ("command", "seq", "done", "body", "error")

    def __init__(self, command: str, seq: int) -> None:
        self.command = command
        self.seq = seq
        self.done = threading.Event()
        self.body: Any = None
        self.error: BaseException | None = None


class DapPeer:
    """A live DAP connection. Start it, call it, stop it."""

    def __init__(self, outgoing: BinaryIO, incoming: BinaryIO, *, framing,
                 handler: Handler | None = None,
                 observer: Observer | None = None,
                 name: str = "dap") -> None:
        self._out = outgoing
        self._in = incoming
        self._framing = framing
        self._name = name
        self._handler: Handler = handler or RejectAll()
        self._observer = observer
        # The specification numbers messages from one. Nothing depends on the
        # first value, but an adapter that logs sequence numbers is easier to
        # read beside a client that counts the same way.
        self._seq = itertools.count(1)
        self._pending: dict[int, Pending] = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._closed = threading.Event()
        self.malformed: list[str] = []
        self.failure_reason: BaseException | None = None

    # -- lifecycle -----------------------------------------------------------

    @property
    def handler(self) -> Handler:
        return self._handler

    @handler.setter
    def handler(self, handler: Handler) -> None:
        """Install this side's answers. A client builds its handler around the
        connection it is going to answer on, so this is set after construction."""
        self._handler = handler

    def start(self) -> "DapPeer":
        self._reader = threading.Thread(target=self._read_loop,
                                        name=f"{self._name}-reader",
                                        daemon=True)
        self._reader.start()
        return self

    def close(self, reason: BaseException | None = None) -> None:
        """Stop the connection and wake every waiter with the same reason."""
        if self._closed.is_set():
            return
        self.failure_reason = self.failure_reason or reason
        self._closed.set()
        ending = self.failure_reason or ConnectionClosed("connection closed")
        with self._lock:
            waiting, self._pending = list(self._pending.values()), {}
        for pending in waiting:
            pending.error = ending
            pending.done.set()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    # -- sending -------------------------------------------------------------

    def _write(self, message: dict) -> None:
        if self._closed.is_set():
            raise self.failure_reason or ConnectionClosed("connection closed")
        if self._observer is not None:
            self._observer(SENT, message)
        with self._write_lock:
            self._out.write(self._framing.encode(message))
            self._out.flush()

    def send(self, command: str, arguments: object = None) -> Pending:
        """Send a request and return without waiting for the answer.

        The waiter is registered before the bytes go out. An adapter fast enough
        to answer before this call returns would otherwise find no waiter and
        the answer would be dropped as stale.
        """
        seq = next(self._seq)
        pending = Pending(command, seq)
        with self._lock:
            self._pending[seq] = pending
        try:
            self._write(request(seq, command, arguments))
        except BaseException:
            with self._lock:
                self._pending.pop(seq, None)
            raise
        return pending

    def await_reply(self, pending: Pending, *, timeout: float = 120.0) -> Any:
        """Wait for one sent request. Raises AdapterError on a failed response."""
        if not pending.done.wait(timeout):
            with self._lock:
                self._pending.pop(pending.seq, None)
            raise TimeoutError(f"{pending.command} did not answer within "
                               f"{timeout:g}s")
        if pending.error is not None:
            raise pending.error
        return pending.body

    def call(self, command: str, arguments: object = None, *,
             timeout: float = 120.0) -> Any:
        """Send a request and wait for its answer."""
        return self.await_reply(self.send(command, arguments), timeout=timeout)

    # -- receiving -----------------------------------------------------------

    def _read_loop(self) -> None:
        try:
            while True:
                frame = self._framing.read(self._in)
                if frame is None:
                    break
                self._on_frame(frame)
        except BaseException as exc:  # noqa: BLE001 - re-raised to every waiter
            self.close(exc)
            return
        self.close(ConnectionClosed("the adapter's stream ended"))

    def _on_frame(self, frame: DapFrame) -> None:
        if frame.malformed:
            # Kept rather than raised. The length was good, so the stream is
            # still aligned, and a client that dropped the session over one
            # unusable message would lose the rest of the run with it.
            self.malformed.append(frame.malformed)
            return
        message = frame.message
        if message is None:
            return
        if self._observer is not None:
            self._observer(RECEIVED, message)
        self._route(message, frame.kind)

    def _route(self, message: dict, kind: str) -> None:
        if kind == RESPONSE:
            self._settle(message)
        elif kind == REQUEST:
            # On its own thread: a handler is allowed to call back into the peer
            # while answering, and answering on the reader thread would deadlock
            # that against its own response.
            threading.Thread(target=self._answer, args=(message,),
                             name=f"{self._name}-answer", daemon=True).start()
        elif kind == EVENT:
            self._handler.on_event(message["event"], message.get("body") or {})

    def _settle(self, message: dict) -> None:
        with self._lock:
            pending = self._pending.pop(message["request_seq"], None)
        if pending is None:
            return  # an answer to a request this side already gave up on
        if message["success"]:
            pending.body = message.get("body")
        else:
            pending.error = AdapterError(message.get("command", ""),
                                         message.get("message", ""),
                                         message.get("body"))
        pending.done.set()

    def _answer(self, message: dict) -> None:
        request_seq, command = message["seq"], message["command"]
        try:
            body = self._handler.on_request(command,
                                            message.get("arguments") or {})
        except CommandNotSupported:
            self._reply_error(request_seq, command,
                              f"this client does not support {command}")
        except Exception as exc:  # noqa: BLE001 - the adapter is owed an answer
            self._reply_error(request_seq, command, repr(exc))
        else:
            self._reply(request_seq, command, body)

    def _reply(self, request_seq: int, command: str, body: object) -> None:
        self._write(response(next(self._seq), request_seq, command, body))

    def _reply_error(self, request_seq: int, command: str, text: str) -> None:
        """Answer a reverse request with a refusal.

        A refusal is written and not swallowed. An adapter that gets no answer
        at all waits on its own request forever, and the session ends looking
        like a hang rather than like a boundary being held.
        """
        try:
            self._write(error_response(next(self._seq), request_seq, command,
                                       text))
        except ConnectionClosed:
            return
