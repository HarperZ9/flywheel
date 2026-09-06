"""jsonrpc_peer.py -- one JSON-RPC peer over a pair of byte streams.

A peer sends calls and answers them. Which methods it answers is the handler's
business, which bytes delimit a message is the framing's, and neither of those
is this file. That split is why ACP and LSP share one implementation of the
part that is easy to get wrong: request ids, the table of waiters, the write
lock, and the rule about which thread may answer.

The observer seam is the reason this layer exists rather than the calls being
inlined. Every message that crosses in either direction is handed to the
observer before anything acts on it, which is where a Flywheel run ledger
attaches. A receipt over a delegated run is only worth reading if the record
was taken at the wire and not reconstructed afterwards from what the far side
chose to summarize.

Threads, not asyncio: the reader owns one blocking read and nothing else, which
matches how harness/cross_harness_process.py already owns child processes and
keeps this usable from the synchronous CLIs.
"""
from __future__ import annotations

import itertools
import threading
from typing import Any, BinaryIO, Callable, Protocol

from .jsonrpc import (FAILURE, INTERNAL_ERROR, INVALID_PARAMS,
                      METHOD_NOT_FOUND, NOTIFICATION, REQUEST, RESPONSE, Frame,
                      classify, failure, notification, request, success)

SENT = "sent"
RECEIVED = "received"

Observer = Callable[[str, dict], None]


class ConnectionClosed(RuntimeError):
    """The peer's stream ended, or this side shut the connection down."""


class MethodNotFound(LookupError):
    """This side does not implement the method the peer called."""


class InvalidParams(ValueError):
    """The peer called a method this side has, with parameters it cannot use."""


class PeerError(RuntimeError):
    """An error response from the peer. The code is the thing to branch on.

    Written by hand rather than as a dataclass because an exception carries
    `args` and a traceback, and a frozen dataclass quietly leaves both empty.
    """

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"{message} (code {code})")
        self.code = int(code)
        self.message = message
        self.data = data


class Framing(Protocol):
    """How a message becomes bytes, and how bytes become messages again."""

    def encode(self, message: dict) -> bytes:
        """Serialize one message, delimiters included."""

    def read(self, stream: BinaryIO) -> Frame | None:
        """Read the next unit of stream, or None once the stream has ended.

        A fault the far side can recover from comes back on the frame and is
        answered. A fault that leaves the stream at an unknown offset is raised,
        because reading on from there would invent messages nobody sent.
        """


class Handler(Protocol):
    """What a peer answers. Both hooks are optional in behaviour, not in shape."""

    def on_request(self, method: str, params: dict) -> object:
        """Return the result for one call, or raise MethodNotFound."""

    def on_notification(self, method: str, params: dict) -> None:
        """Act on one one-way message. A raise here fails the connection."""


class RejectAll:
    """The default handler: answers nothing, ignores nothing silently."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, dict]] = []

    def on_request(self, method: str, params: dict) -> object:
        raise MethodNotFound(method)

    def on_notification(self, method: str, params: dict) -> None:
        self.seen.append((method, params))


class _Pending:
    __slots__ = ("done", "result", "error")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


class Peer:
    """A live JSON-RPC peer. Start it, call it, stop it."""

    def __init__(self, outgoing: BinaryIO, incoming: BinaryIO, *,
                 framing: Framing, handler: Handler | None = None,
                 observer: Observer | None = None,
                 name: str = "jsonrpc") -> None:
        self._out = outgoing
        self._in = incoming
        self._framing = framing
        self._name = name
        self._handler: Handler = handler or RejectAll()
        self._observer = observer
        self._ids = itertools.count(0)
        self._pending: dict[Any, _Pending] = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._closed = threading.Event()
        self.failure_reason: BaseException | None = None

    # -- lifecycle -----------------------------------------------------------

    @property
    def handler(self) -> Handler:
        return self._handler

    @handler.setter
    def handler(self, handler: Handler) -> None:
        """Install the peer's answers. A client builds its handler around the
        connection it is going to answer on, so this is set after construction."""
        self._handler = handler

    def start(self):
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

    def _send(self, message: dict) -> None:
        if self._closed.is_set():
            raise self.failure_reason or ConnectionClosed("connection closed")
        if self._observer is not None:
            self._observer(SENT, message)
        with self._write_lock:
            self._out.write(self._framing.encode(message))
            self._out.flush()

    def notify(self, method: str, params: object = None) -> None:
        self._send(notification(method, params))

    def call(self, method: str, params: object = None, *,
             timeout: float = 600.0) -> Any:
        """Call the peer and wait. Raises PeerError on an error response."""
        request_id = next(self._ids)
        pending = _Pending()
        with self._lock:
            self._pending[request_id] = pending
        self._send(request(request_id, method, params))
        if not pending.done.wait(timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise TimeoutError(f"{method} did not answer within {timeout:g}s")
        if pending.error is not None:
            raise pending.error
        return pending.result

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
        self.close(ConnectionClosed("the peer's stream ended"))

    def _on_frame(self, frame: Frame) -> None:
        for fault in frame.faults:
            self._send(fault)
        for message in frame.messages:
            if self._observer is not None:
                self._observer(RECEIVED, message)
            self._route(message)

    def _route(self, message: dict) -> None:
        kind = classify(message)
        if kind in (RESPONSE, FAILURE):
            self._settle(message, kind)
        elif kind == REQUEST:
            # On its own thread: a handler is allowed to call back into the peer
            # (a permission prompt that reads a file, say), and answering on the
            # reader thread would deadlock that against its own response.
            threading.Thread(target=self._answer, args=(message,),
                             name=f"{self._name}-answer", daemon=True).start()
        elif kind == NOTIFICATION:
            self._handler.on_notification(message["method"],
                                          message.get("params") or {})

    def _settle(self, message: dict, kind: str) -> None:
        with self._lock:
            pending = self._pending.pop(message["id"], None)
        if pending is None:
            return  # an answer to a request this side already gave up on
        if kind == FAILURE:
            error = message["error"]
            pending.error = PeerError(error["code"], error.get("message", ""),
                                      error.get("data"))
        else:
            pending.result = message["result"]
        pending.done.set()

    def _answer(self, message: dict) -> None:
        request_id, method = message["id"], message["method"]
        try:
            result = self._handler.on_request(method,
                                              message.get("params") or {})
        except MethodNotFound:
            self._send(failure(request_id, METHOD_NOT_FOUND, method))
        except InvalidParams as exc:
            self._send(failure(request_id, INVALID_PARAMS, str(exc)))
        except Exception as exc:  # noqa: BLE001 - the peer is owed an answer
            self._send(failure(request_id, INTERNAL_ERROR, repr(exc)))
        else:
            self._send(success(request_id, result))
