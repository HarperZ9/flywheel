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

import threading
import time

from .dap_wire import (ATTACH, CONFIGURATION_DONE, CONTINUED, EXITED,
                       INITIALIZE, INITIALIZED, LAUNCH, OUTPUT,
                       RUN_IN_TERMINAL, SET_BREAKPOINTS,
                       SET_EXCEPTION_BREAKPOINTS, START_DEBUGGING, STOPPED,
                       TERMINATED)
from .dap_peer import CommandNotSupported, DapPeer
# Re-exported: a caller that holds a session reads `Stop` off it and declares
# capabilities alongside it, so importing those from two modules would be a
# seam nobody asked for. What they are is in `dap_state`.
from .dap_state import (Events, Stop, client_capabilities,  # noqa: F401
                        stop_from)

#: What one request waits before this side stops waiting. An adapter starting a
#: program under a debugger is slow once, not slow forever.
DEFAULT_TIMEOUT = 30.0

__all__ = ["DEFAULT_TIMEOUT", "DapSession", "Stop", "client_capabilities"]


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
        self._exited = threading.Event()
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
            self.stop = stop_from(body)
            self._stopped.set()
        elif name == CONTINUED:
            self.stop = None
            self._stopped.clear()
        elif name == OUTPUT:
            self.events.output.append(body)
        elif name == EXITED:
            code = body.get("exitCode")
            self.events.exit_code = code if isinstance(code, int) else None
            self._exited.set()
        elif name == TERMINATED:
            self._terminated.set()

    @property
    def terminated(self) -> bool:
        return self._terminated.is_set()

    @property
    def exited(self) -> bool:
        """Whether the `exited` event arrived. Not the same as `terminated`.

        The protocol orders neither event, and real adapters disagree: some send
        `exited` first, some send `terminated` first. A caller that waits on
        `terminated` and then reads `exit_code` gets None from half of them.
        """
        return self._exited.is_set()

    def settle_exit(self, timeout: float = 0.5) -> int | None:
        """The exit code, once the two end-of-session events have both landed.

        A program that is still running reports None without waiting. Once
        either end event has arrived this waits out the other, so a reader
        cannot catch the pair half-written and record a run as terminated with
        no exit code.

        Returns None when the adapter ended the session without an `exited`
        event, which an attach or a detach does. None is the honest answer
        there and 0 would be a fabricated success.

        The timeout is what that case costs, not a guess at how fast an adapter
        is. An adapter that sends both writes them back to back on one stream,
        so the gap being waited out is sub-millisecond; a session that ends with
        no `exited` at all pays the whole number every time, which is why it is
        small.
        """
        if self._terminated.is_set() or self._exited.is_set():
            self._exited.wait(timeout)
        return self.events.exit_code

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
