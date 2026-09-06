"""dap_policy.py -- what a Flywheel DAP client will let a debug adapter do.

A debug adapter has one way to reach past the program being debugged, and it is
the two reverse requests. `runInTerminal` asks the client to start a process,
with the command line, the working directory and the environment all chosen by
the adapter. `startDebugging` asks the client to open a second debug session
against a configuration the adapter supplies. Everything else an adapter sends
is a report about the debuggee.

So the grant boundary is those two, and it is written as its own module for the
same reason harness/acp_policy.py is: a boundary buried inside a transport is a
boundary nobody audits.

The default is DenyAll. A harness whose job is to witness a run should not also
be the thing that authorized it by omission. An adapter refused here says so in
its own output, which is a better record than a silent allow.

Every decision is recorded on the policy object, and the witness reads those
records back. A receipt then says what the adapter asked for as well as what it
was given, and the refusals are the part a reader cannot reconstruct from the
outcome.
"""
from __future__ import annotations

from pathlib import Path
import shlex
from typing import Any, Protocol

from .acp_policy import Decision
from .dap_wire import RUN_IN_TERMINAL, START_DEBUGGING

# Which terminal the adapter asked for. `external` opens a window outside the
# client, which puts the process further out of reach of anything watching, so a
# policy that allows one kind does not thereby allow the other.
INTEGRATED = "integrated"
EXTERNAL = "external"

__all__ = ["AllowTerminal", "Decision", "DenyAll", "EXTERNAL", "INTEGRATED",
           "OutsideRoot", "Policy", "describe"]


class OutsideRoot(PermissionError):
    """A working directory the adapter asked for that lies outside the root."""


class Policy(Protocol):
    """The two questions a debug adapter can ask its client."""

    name: str

    def run_in_terminal(self, arguments: dict) -> dict: ...

    def start_debugging(self, arguments: dict) -> dict: ...


def describe(command: str, arguments: dict) -> str:
    """One line naming what was asked for, for the record and for a reader.

    Argument values are kept. The whole point of the record is that somebody can
    later read what the adapter wanted to run, and a redacted command line
    answers a question nobody asked.
    """
    if command == RUN_IN_TERMINAL:
        argv = arguments.get("args")
        line = shlex.join([str(part) for part in argv]) if isinstance(argv, list) else ""
        cwd = str(arguments.get("cwd", ""))
        kind = str(arguments.get("kind", INTEGRATED))
        return f"{kind} terminal in {cwd or 'no cwd'}: {line or 'no command'}"
    if command == START_DEBUGGING:
        configuration = arguments.get("configuration")
        name = ""
        if isinstance(configuration, dict):
            name = str(configuration.get("name") or configuration.get("type") or "")
        return f"{arguments.get('request', 'launch')} session {name or 'unnamed'}"
    return command


class DenyAll:
    """Refuse both reverse requests, record each one, and debug anyway.

    This is the default. A debug session under DenyAll still runs: an adapter
    that cannot get a terminal reports that it could not, and the breakpoints,
    stack frames and variables that make up the rest of the session are
    unaffected. What the operator gets is a run with no process started on their
    behalf and a record of the one that was asked for.
    """

    name = "deny-all"

    def __init__(self) -> None:
        self.decisions: list[Decision] = []

    def _record(self, command: str, arguments: dict, allowed: bool,
                reason: str = "") -> None:
        self.decisions.append(Decision(command, describe(command, arguments),
                                       allowed, reason))

    def run_in_terminal(self, arguments: dict) -> dict:
        self._record(RUN_IN_TERMINAL, arguments, False,
                     "policy starts no process for an adapter")
        raise PermissionError("this client does not start processes for the "
                              "adapter")

    def start_debugging(self, arguments: dict) -> dict:
        self._record(START_DEBUGGING, arguments, False,
                     "policy opens no second session")
        raise PermissionError("this client does not open a second debug "
                              "session")


class AllowTerminal(DenyAll):
    """Start the process the adapter asked for, inside one directory.

    The narrow allow, for the case a debug session needs: an adapter that cannot
    launch the debuggee itself and asks the client to do it. `startDebugging`
    stays refused, because a second session is a second adapter with its own
    reach and no record attached to it.

    Handing back a real process id matters. The specification lets a client
    answer with an empty body, and an adapter that gets one cannot terminate what
    it started, so the process outlives the session it belonged to.
    """

    name = "allow-terminal"

    def __init__(self, root: Path | str, *, spawn=None,
                 allow_external: bool = False) -> None:
        super().__init__()
        self.root = Path(root).resolve()
        self.allow_external = allow_external
        # Injected so a test can watch what would have been started without
        # starting it, and so the caller decides how a process is launched.
        self._spawn = spawn if spawn is not None else _spawn_detached

    def run_in_terminal(self, arguments: dict) -> dict:
        kind = str(arguments.get("kind", INTEGRATED))
        if kind == EXTERNAL and not self.allow_external:
            self._record(RUN_IN_TERMINAL, arguments, False,
                         "policy allows an integrated terminal only")
            raise PermissionError("this client does not open an external "
                                  "terminal")
        argv = arguments.get("args")
        if not isinstance(argv, list) or not argv:
            self._record(RUN_IN_TERMINAL, arguments, False,
                         "the adapter named no command")
            raise ValueError("runInTerminal carries a non-empty args list")
        try:
            cwd = self._inside(arguments.get("cwd"))
        except OutsideRoot as exc:
            self._record(RUN_IN_TERMINAL, arguments, False, str(exc))
            raise
        process_id = self._spawn([str(part) for part in argv], cwd,
                                 arguments.get("env"))
        self._record(RUN_IN_TERMINAL, arguments, True)
        return {"processId": process_id}

    def _inside(self, raw: Any) -> Path:
        """The working directory, refused unless it is at or under the root.

        Resolved before comparing, because a symlink inside the root pointing
        out of it is the ordinary way a check that compares strings is walked
        through. An adapter that names no cwd gets the root itself, which is the
        narrowest answer available rather than the process's own directory.

        A relative path is read against the root for the same reason. Adapters
        send `.` and `${workspaceFolder}/x` routinely, and resolving those
        against whatever directory this client was started in would name a
        place the adapter never meant and the root was never checked against.
        A traversal out is still resolved and still refused below.
        """
        if raw in (None, ""):
            return self.root
        if not isinstance(raw, str):
            raise OutsideRoot(f"cwd is a path, got {type(raw).__name__}")
        wanted = Path(raw)
        resolved = (wanted if wanted.is_absolute()
                    else self.root / wanted).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise OutsideRoot(f"{resolved} is outside {self.root}")
        return resolved


def _spawn_detached(argv: list[str], cwd: Path, env: Any) -> int:
    """Start the process and return its id, without a shell.

    No shell, so the argument list the adapter sent is the argument list that
    runs and nothing in it is reinterpreted as syntax. The environment is the
    client's, with the adapter's additions layered on: a null value means unset,
    which is how the specification spells removing a variable.
    """
    import os
    import subprocess

    environment = dict(os.environ)
    if isinstance(env, dict):
        for name, value in env.items():
            if value is None:
                environment.pop(str(name), None)
            else:
                environment[str(name)] = str(value)
    process = subprocess.Popen(argv, cwd=str(cwd), env=environment)
    return process.pid
