"""dap_session.py -- the DAP lifecycle, in the order that survives both readings.

The specification is read two ways on one point, and a client that picks either
reading works against half the adapters. The sequence page shows `launch` sent
and its response awaited before configuration; the overview shows configuration
happening between `initialized` and the launch response. Real adapters split the
same way: some answer `launch` only after `configurationDone`, and a client that
blocks on the launch response first deadlocks against them.

What works against both is to stop treating `launch` as a call. Send it, leave it
in flight, wait for the `initialized` event, configure, send `configurationDone`,
and only then collect the launch response. An adapter that answered early has
its answer waiting; one that answers late gets what it was waiting for.

This module is also where events are kept. A debug adapter says most of what it
has to say in events rather than in responses, and an adapter that stops at a
breakpoint has already sent `stopped` by the time any request could ask.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time

from .dap_wire import (ATTACH, CONFIGURATION_DONE, CONTINUED, EXITED,
                       INITIALIZE, INITIALIZED, LAUNCH, OUTPUT,
                       RUN_IN_TERMINAL, SET_BREAKPOINTS,
                       SET_EXCEPTION_BREAKPOINTS, START_DEBUGGING, STOPPED,
                       TERMINATED)
from .dap_peer import CommandNotSupported, DapPeer

#: What one request waits before this side stops waiting. An adapter starting a
#: program under a debugger is slow once, not slow forever.
DEFAULT_TIMEOUT = 30.0

__all__ = ["DEFAULT_TIMEOUT", "DapSession", "Stop", "client_capabilities"]


@dataclass(frozen=True)
class Stop:
    """One `stopped` event, in the shape a caller asks questions about."""

    reason: str = ""
    thread_id: int | None = None
    description: str = ""
    text: str = ""
    all_threads: bool = False
    hit_breakpoint_ids: tuple = ()


@dataclass
class Events:
    """What the adapter said while nothing was asking.

    Kept whole rather than folded, because the fold belongs to the witness and a
    session that threw away an event it did not recognize would make the record
    a summary of what this client understood rather than of what crossed.
    """

    seen: list[tuple[str, dict]] = field(default_factory=list)
    output: list[dict] = field(default_factory=list)
    exit_code: int | None = None


def client_capabilities(adapter_id: str, *, lines_start_at_one: bool = True,
                        columns_start_at_one: bool = True) -> dict:
    """The initialize arguments, declared rather than guessed.

    `supportsRunInTerminalRequest` and `supportsStartDebuggingRequest` are true
    because this client does answer both, and the answer is a refusal under the
    default policy. Declaring false would be a different statement: it tells the
    adapter not to ask, and then the record shows nothing where a request and a
    refusal belong. The boundary is worth more when it is exercised.

    Line and column bases are declared once here and are the only reason the
    numbers in a stack frame mean anything. An adapter is free to count from
    zero and will, unless it is told.
    """
    return {"clientID": "flywheel", "clientName": "Flywheel",
            "adapterID": str(adapter_id), "locale": "en-US",
            "linesStartAt1": bool(lines_start_at_one),
            "columnsStartAt1": bool(columns_start_at_one),
            "pathFormat": "path",
            "supportsVariableType": True,
            "supportsVariablePaging": False,
            "supportsRunInTerminalRequest": True,
            "supportsStartDebuggingRequest": True,
            "supportsMemoryReferences": False,
            "supportsProgressReporting": False,
            "supportsInvalidatedEvent": False,
            "supportsMemoryEvent": False}


class DapSession:
    """One adapter's lifecycle and everything it said along the way.

    Installed as the peer's handler, so reverse requests reach the policy and
    events land here without anything having to poll.
    """

    def __init__(self, peer: DapPeer, policy) -> None:
        self.peer = peer
        self.policy = policy
        self.capabilities: dict = {}
        self.events = Events()
        self.stop: Stop | None = None
        self.breakpoints: dict[str, list] = {}
        self._initialized = threading.Event()
        self._stopped = threading.Event()
        self._terminated = threading.Event()
        peer.handler = self

    # -- what the adapter sends unasked -------------------------------------

    def on_request(self, command: str, arguments: dict) -> object:
        """The two reverse requests, answered by the policy and nothing else."""
        if command == RUN_IN_TERMINAL:
            return self.policy.run_in_terminal(arguments)
        if command == START_DEBUGGING:
            return self.policy.start_debugging(arguments)
        raise CommandNotSupported(command)

    def on_event(self, name: str, body: dict) -> None:
        self.events.seen.append((name, body))
        if name == INITIALIZED:
            self._initialized.set()
        elif name == STOPPED:
            self.stop = _stop_from(body)
            self._stopped.set()
        elif name == CONTINUED:
            self.stop = None
            self._stopped.clear()
        elif name == OUTPUT:
            self.events.output.append(body)
        elif name == EXITED:
            code = body.get("exitCode")
            self.events.exit_code = code if isinstance(code, int) else None
        elif name == TERMINATED:
            self._terminated.set()

    @property
    def terminated(self) -> bool:
        return self._terminated.is_set()

    def clear_stop(self) -> None:
        """Forget where the program was stopped, before resuming it.

        Called before the resume request rather than after its reply, because a
        `stopped` event for the next breakpoint can arrive first and clearing
        afterwards would erase the stop the caller is about to ask about.
        """
        self.stop = None
        self._stopped.clear()

    def wait_for_stop(self, timeout: float = DEFAULT_TIMEOUT) -> Stop | None:
        """Wait for the program to stop. None means it did not, in time.

        A terminated program ends the wait early. Waiting the full timeout for a
        breakpoint in a process that has already exited reports a slow adapter
        where the honest answer is that the breakpoint was never hit.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._stopped.wait(0.05):
                return self.stop
            if self._terminated.is_set():
                return None
        return None

    # -- the lifecycle -------------------------------------------------------

    def start(self, adapter_id: str, *, launch: dict | None = None,
              attach: dict | None = None,
              breakpoints: dict | None = None,
              exception_filters: list | None = None,
              timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Bring the session up, in the order both readings of the spec allow.

        Returns the launch or attach response body. Exactly one of `launch` and
        `attach` is given: they are the two ways a session begins and an adapter
        offered both has been told two different things about what it is doing.
        """
        if (launch is None) == (attach is None):
            raise ValueError("a session is launched or attached, not both "
                             "and not neither")
        self.capabilities = self._initialize(adapter_id, timeout)
        command = LAUNCH if launch is not None else ATTACH
        pending = self.peer.send(command, launch if launch is not None
                                 else attach)
        self._await_initialized(pending, timeout)
        self._configure(breakpoints or {}, exception_filters, timeout)
        return self.peer.await_reply(pending, timeout=timeout)

    def _initialize(self, adapter_id: str, timeout: float) -> dict:
        result = self.peer.call(INITIALIZE, client_capabilities(adapter_id),
                                timeout=timeout)
        return result if isinstance(result, dict) else {}

    def _await_initialized(self, pending, timeout: float) -> bool:
        """Wait for the `initialized` event, and give up when it cannot come.

        An adapter that failed its launch outright answers the request and never
        sends the event. Waiting on the event alone would turn that failure into
        a timeout and hide the reason, so a settled launch ends the wait and the
        reason surfaces when the response is collected.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._initialized.wait(0.05):
                return True
            if pending.done.is_set() or self.peer.closed:
                return False
        return False

    def _configure(self, breakpoints: dict, exception_filters: list | None,
                   timeout: float) -> None:
        """Set breakpoints, then say configuration is over.

        `configurationDone` is sent only when the adapter said it takes one.
        Sending it to an adapter that did not advertise support earns an error
        response, and the error is indistinguishable at this level from the
        launch having failed.
        """
        for path, lines in breakpoints.items():
            self.set_breakpoints(path, lines, timeout=timeout)
        if exception_filters is not None:
            self.peer.call(SET_EXCEPTION_BREAKPOINTS,
                           {"filters": list(exception_filters)},
                           timeout=timeout)
        if self.capabilities.get("supportsConfigurationDoneRequest"):
            self.peer.call(CONFIGURATION_DONE, {}, timeout=timeout)

    def set_breakpoints(self, path: str, lines, *,
                        timeout: float = DEFAULT_TIMEOUT) -> list:
        """Set every breakpoint for one source, and keep what came back.

        The reply is the record that matters. An adapter is allowed to answer a
        breakpoint with `verified: false` or to move it to another line, and a
        client that reported the request rather than the reply would be
        reporting a breakpoint that is not there.
        """
        wanted = [{"line": int(line)} for line in lines]
        result = self.peer.call(SET_BREAKPOINTS,
                                {"source": {"path": str(path)},
                                 "breakpoints": wanted,
                                 "lines": [entry["line"] for entry in wanted]},
                                timeout=timeout)
        placed = (result or {}).get("breakpoints") or []
        self.breakpoints[str(path)] = placed
        return placed

    def verified_breakpoints(self) -> tuple[int, int]:
        """How many breakpoints the adapter took, out of how many were asked.

        Two numbers rather than a pass or fail, because an unverified breakpoint
        is the ordinary case for a file the debuggee has not loaded yet and not
        by itself a failure.
        """
        placed = [entry for entries in self.breakpoints.values()
                  for entry in entries]
        verified = [entry for entry in placed
                    if isinstance(entry, dict) and entry.get("verified")]
        return len(verified), len(placed)


def _stop_from(body: dict) -> Stop:
    thread_id = body.get("threadId")
    hits = body.get("hitBreakpointIds")
    return Stop(reason=str(body.get("reason", "")),
                thread_id=thread_id if isinstance(thread_id, int) else None,
                description=str(body.get("description", "")),
                text=str(body.get("text", "")),
                all_threads=bool(body.get("allThreadsStopped")),
                hit_breakpoint_ids=tuple(hits) if isinstance(hits, list) else ())
