"""dap_client.py -- drive a debug adapter as a subprocess and keep the record.

A debugger is the one tool an agent uses whose observations nobody can check
afterwards. An agent that says a variable held a certain value at a certain line
is reporting something that existed for a moment inside a process that is gone.
This client speaks the Debug Adapter Protocol and chains every message that
crossed the wire, so the claim and the wire it came off stay attached.

The pieces are separate on purpose. The envelope is harness/dap_wire.py, the
connection is harness/dap_peer.py, the lifecycle is harness/dap_session.py, the
grant boundary is harness/dap_policy.py, and the chain is
harness/dap_witness.py. What is here is the assembly and the inspection calls a
caller actually makes.

Inspection is read-only by construction. There is no setVariable, no
setExpression, and `evaluate` is sent in the `watch` context rather than `repl`,
because a client whose job is to observe a program should not be the thing that
changed it. An adapter that offers more is not asked.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Sequence

from .child_stdio import settled, spawn, text_of
from .dap_peer import DapPeer, Observer
from .dap_policy import DenyAll
from .dap_session import DEFAULT_TIMEOUT, DapSession, Stop
from .dap_wire import (CONTINUE, DISCONNECT, EVALUATE, NEXT, PAUSE, SCOPES,
                       STACK_TRACE, STEP_IN, STEP_OUT, TERMINATE, THREADS,
                       VARIABLES, DapFraming)

#: How deep a stack trace is read by default. A stack is unbounded in principle
#: and a runaway recursion is exactly the bug somebody attaches a debugger to,
#: so the read is capped and the cap is on the record rather than implied.
DEFAULT_STACK_LEVELS = 64

__all__ = ["DEFAULT_STACK_LEVELS", "DEFAULT_TIMEOUT", "DapClient", "Stop"]


class DapClient:
    """One debug adapter, from spawn to exit."""

    def __init__(self, peer: DapPeer, *, policy=None,
                 process: subprocess.Popen | None = None,
                 root: Path | None = None,
                 stderr: list[bytes] | None = None) -> None:
        self.peer = peer
        self.policy = policy if policy is not None else DenyAll()
        self.process = process
        self.root = root
        self.session = DapSession(peer, self.policy)
        self._stderr = stderr if stderr is not None else []

    @classmethod
    def start(cls, argv: Sequence[str], *, root: Path | str | None = None,
              policy=None, observer: Observer | None = None,
              env: dict[str, str] | None = None) -> "DapClient":
        """Start a debug adapter and connect to its stdio."""
        directory = Path(root or Path.cwd()).resolve()
        process, collected = spawn(argv, directory, env=env, name="dap")
        peer = DapPeer(process.stdin, process.stdout, framing=DapFraming(),
                       observer=observer)
        client = cls(peer, policy=policy, process=process, root=directory,
                     stderr=collected)
        peer.start()
        return client

    def __enter__(self) -> "DapClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- lifecycle -----------------------------------------------------------

    def start_session(self, adapter_id: str, **kwargs) -> dict:
        """Bring the session up. See harness/dap_session.py for the ordering."""
        return self.session.start(adapter_id, **kwargs)

    @property
    def capabilities(self) -> dict:
        return self.session.capabilities

    def supports(self, capability: str) -> bool:
        """Whether the adapter advertised a capability, by its own name for it."""
        return self.session.capabilities.get(capability) is True

    def wait_for_stop(self, timeout: float = DEFAULT_TIMEOUT) -> Stop | None:
        return self.session.wait_for_stop(timeout)

    def disconnect(self, *, terminate: bool = True,
                   timeout: float = DEFAULT_TIMEOUT) -> None:
        """End the session, leaving no debuggee running behind it.

        `terminate` is tried first when the adapter takes it, because
        `disconnect` alone lets the debuggee keep running under some adapters and
        a harness that leaked a live process every run would be worse than one
        that never attached. Nothing raises: this is the exit path, and an
        adapter that has already died is a normal way to arrive here.
        """
        try:
            if terminate and self.supports("supportsTerminateRequest"):
                self.peer.call(TERMINATE, {"restart": False}, timeout=timeout)
            self.peer.call(DISCONNECT,
                           {"restart": False, "terminateDebuggee": terminate},
                           timeout=timeout)
        except Exception:  # noqa: BLE001 - the exit path reports by returning
            return

    def close(self, grace: float = 5.0) -> None:
        """Stop the adapter, politely if it is still listening.

        Closing the child's stdin is what ends a stdio adapter that never got a
        disconnect: it reads end-of-file and returns on its own. Without that it
        waits for a message nobody will send, and every close costs the full
        grace period before turning into a kill.
        """
        self.peer.close()
        process = self.process
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=grace)

    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stderr_text(self) -> str:
        """Whatever the adapter wrote to its own error stream, bounded.

        A dead child is waited on first, because the last thing it wrote is
        usually the reason it is dead and the read that misses it reads clean.
        """
        if self.process is not None and self.process.poll() is not None:
            settled(self.process)
        return text_of(self._stderr)

    # -- inspection ----------------------------------------------------------

    def threads(self, timeout: float = DEFAULT_TIMEOUT) -> list:
        result = self.peer.call(THREADS, None, timeout=timeout)
        return (result or {}).get("threads") or []

    def stack_trace(self, thread_id: int, *, start: int = 0,
                    levels: int = DEFAULT_STACK_LEVELS,
                    timeout: float = DEFAULT_TIMEOUT) -> dict:
        """The frames on one thread, and how many there are in total.

        `totalFrames` is kept beside the frames because it is how a reader knows
        the cap was hit. A truncated stack that does not say it was truncated
        reads as a complete one.
        """
        result = self.peer.call(STACK_TRACE,
                                {"threadId": int(thread_id),
                                 "startFrame": int(start),
                                 "levels": int(levels)}, timeout=timeout) or {}
        return {"frames": result.get("stackFrames") or [],
                "total": result.get("totalFrames"),
                "truncated": _truncated(result, start, levels)}

    def scopes(self, frame_id: int, timeout: float = DEFAULT_TIMEOUT) -> list:
        result = self.peer.call(SCOPES, {"frameId": int(frame_id)},
                                timeout=timeout)
        return (result or {}).get("scopes") or []

    def variables(self, reference: int, *, timeout: float = DEFAULT_TIMEOUT,
                  count: int = 0) -> list:
        """One scope's variables. A reference of zero has none by definition."""
        if int(reference) == 0:
            return []
        arguments: dict = {"variablesReference": int(reference)}
        if count:
            arguments["count"] = int(count)
        result = self.peer.call(VARIABLES, arguments, timeout=timeout)
        return (result or {}).get("variables") or []

    def evaluate(self, expression: str, *, frame_id: int | None = None,
                 context: str = "watch",
                 timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Evaluate an expression against a frame, in a read-only context.

        `watch` rather than `repl`. Both evaluate, and adapters treat `repl` as
        a place side effects are expected, down to running debugger commands.
        The context is a request and not a guarantee: an expression that calls a
        function still calls it, which is on the record's does-not-prove list
        rather than defended here.
        """
        arguments: dict = {"expression": str(expression), "context": context}
        if frame_id is not None:
            arguments["frameId"] = int(frame_id)
        return self.peer.call(EVALUATE, arguments, timeout=timeout) or {}

    def frame_variables(self, frame_id: int,
                        timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Every scope on one frame, each with its variables, in one call.

        The shape a caller wants and the shape the protocol makes them assemble
        from three round trips. Expensive scopes are skipped: an adapter marks
        one when reading it costs enough to be noticeable, and paying that for a
        record nobody asked for is how a debug session becomes the slow part.
        """
        collected: dict = {}
        for scope in self.scopes(frame_id, timeout=timeout):
            if not isinstance(scope, dict) or scope.get("expensive"):
                continue
            name = str(scope.get("name", ""))
            collected[name] = self.variables(scope.get("variablesReference", 0),
                                             timeout=timeout)
        return collected

    # -- execution -----------------------------------------------------------

    def resume(self, thread_id: int, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Continue the program. Clears the stop before the reply lands.

        The clear happens first because a `stopped` event for the next
        breakpoint can arrive before the `continue` response does, and clearing
        afterwards would erase the stop this client is about to be asked about.
        """
        self.session.clear_stop()
        return self.peer.call(CONTINUE, {"threadId": int(thread_id)},
                              timeout=timeout) or {}

    def step(self, thread_id: int, *, over: bool = True, out: bool = False,
             timeout: float = DEFAULT_TIMEOUT) -> None:
        """One step, and the stop it earns is waited for by the caller."""
        command = STEP_OUT if out else (NEXT if over else STEP_IN)
        self.session.clear_stop()
        self.peer.call(command, {"threadId": int(thread_id)}, timeout=timeout)

    def pause(self, thread_id: int, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.peer.call(PAUSE, {"threadId": int(thread_id)}, timeout=timeout)


def _truncated(result: dict, start: int, levels: int) -> bool:
    """Whether more frames exist than were read.

    An adapter that reports no total is taken at its word rather than guessed
    about: a full page could mean there is more or could mean the stack is
    exactly that deep, and the record says unknown by saying false only when the
    total is known.
    """
    total = result.get("totalFrames")
    if not isinstance(total, int):
        return False
    return total > start + levels
