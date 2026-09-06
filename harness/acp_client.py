"""acp_client.py -- drive an ACP agent as a subprocess and keep the record.

This is the client half of the Agent Client Protocol: Flywheel spawns an agent
the operator already uses, negotiates a version, opens a session, sends a prompt,
and collects the turn. The point is not to replace that agent. The point is that
a run the operator was going to make anyway leaves a record taken at the wire.

Version negotiation is explicit because both v1 and v2 are deployed and they end
a turn differently. On v2 `session/prompt` returns once the prompt is accepted
and the turn ends when a `session/update` reports idle with a stop reason. On v1
the prompt response carries the stop reason itself. The collector is armed before
the prompt is sent, so an agent fast enough to finish before its own response
lands is handled by the same code path as a slow one.

Nothing here decides what the agent may do. That is acp_policy, and the default
there refuses.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import threading
from typing import Iterable, Sequence

from .acp_connection import Connection, MethodNotFound, Observer, PeerError
from .acp_policy import DenyAll, Policy
from .acp_turn import TurnCollector, Turn
from .acp_wire import (AUTH_REQUIRED, INVALID_PARAMS, PROTOCOL_VERSION,
                       SUPPORTED_VERSIONS)
from .child_stdio import spawn

SESSION_UPDATE = "session/update"
REQUEST_PERMISSION = "session/request_permission"
READ_TEXT_FILE = "fs/read_text_file"
WRITE_TEXT_FILE = "fs/write_text_file"



class AuthRequired(RuntimeError):
    """The agent will not work until the operator signs in to it themselves."""


class VersionUnsupported(RuntimeError):
    """The agent answered with a protocol major version this client cannot read."""


class ClientHandler:
    """Answers what an ACP agent asks of its client, and nothing else.

    A method this client did not declare support for is answered with method not
    found rather than a stub. An agent reads that as a capability it does not
    have, which is true, and picks another route.
    """

    def __init__(self, policy: Policy, deliver) -> None:
        self._policy = policy
        self._deliver = deliver

    def on_request(self, method: str, params: dict) -> object:
        if method == REQUEST_PERMISSION:
            return self._policy.permission(params)
        if method == READ_TEXT_FILE:
            return self._policy.read_text_file(params)
        if method == WRITE_TEXT_FILE:
            return self._policy.write_text_file(params)
        raise MethodNotFound(method)

    def on_notification(self, method: str, params: dict) -> None:
        if method == SESSION_UPDATE:
            self._deliver(params)


def _client_capabilities(policy: Policy) -> dict:
    """Say what this client will actually do, so the agent plans around it.

    Taken from the policy's declared flags rather than by trying a call.
    Advertising a capability the policy then refuses makes every refusal look
    like a fault, and probing a write capability would mean writing something.
    """
    return {
        "fs": {"readTextFile": bool(getattr(policy, "reads", False)),
               "writeTextFile": bool(getattr(policy, "writes", False))},
        "terminal": False,
    }


class AcpClient:
    """One ACP agent, from spawn to close."""

    def __init__(self, connection: Connection, *, policy: Policy | None = None,
                 process: subprocess.Popen | None = None,
                 stderr: list[bytes] | None = None) -> None:
        self.policy: Policy = policy or DenyAll()
        self.process = process
        self.protocol_version = 0
        self.agent_capabilities: dict = {}
        self.agent_info: dict = {}
        self.auth_methods: list = []
        self.session_id = ""
        self.stray_updates: list[dict] = []
        self._stderr = stderr if stderr is not None else []
        self._turns: dict[str, tuple[TurnCollector, threading.Event]] = {}
        self._lock = threading.Lock()
        self._conn = connection
        connection.handler = ClientHandler(self.policy, self._deliver)

    # -- construction --------------------------------------------------------

    @classmethod
    def spawn(cls, argv: Sequence[str], *, cwd: Path | str | None = None,
              policy: Policy | None = None, observer: Observer | None = None,
              env: dict[str, str] | None = None) -> "AcpClient":
        """Start an agent and connect to its stdio."""
        directory = Path(cwd or Path.cwd()).resolve()
        process, collected = spawn(argv, directory, env=env, name="acp")
        connection = Connection(process.stdin, process.stdout,
                                observer=observer)
        client = cls(connection, policy=policy, process=process,
                     stderr=collected)
        connection.start()
        return client

    def __enter__(self) -> "AcpClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- lifecycle -----------------------------------------------------------

    def initialize(self, *, name: str = "flywheel", title: str = "Flywheel",
                   version: str = "0", timeout: float = 30.0) -> dict:
        """Negotiate. The agent answers with the version it will actually speak.

        v2 renamed two initialize fields, so a v1 agent rejects the v2 params
        outright. The retry sends the v1 names rather than sending both at once,
        because an agent that validates its params strictly would refuse a
        message carrying the pair.
        """
        capabilities = _client_capabilities(self.policy)
        info = {"name": name, "title": title, "version": version}
        try:
            result = self._call("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": capabilities, "info": info}, timeout=timeout)
        except PeerError as exc:
            if exc.code != INVALID_PARAMS:
                raise
            result = self._call("initialize", {
                "protocolVersion": 1, "clientCapabilities": capabilities,
                "clientInfo": info}, timeout=timeout)
        spoken = result.get("protocolVersion")
        if spoken not in SUPPORTED_VERSIONS:
            raise VersionUnsupported(
                f"the agent speaks protocol version {spoken!r}; "
                f"this client speaks {SUPPORTED_VERSIONS}")
        self.protocol_version = int(spoken)
        self.agent_capabilities = result.get("capabilities") or {}
        self.agent_info = result.get("info") or result.get("agentInfo") or {}
        self.auth_methods = list(result.get("authMethods") or [])
        return result

    def new_session(self, cwd: Path | str | None = None, *,
                    mcp_servers: Iterable[dict] = (),
                    timeout: float = 60.0) -> str:
        directory = Path(cwd or Path.cwd()).resolve()
        result = self._call("session/new",
                            {"cwd": str(directory),
                             "mcpServers": list(mcp_servers)}, timeout=timeout)
        session_id = result.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session/new answered without a sessionId")
        self.session_id = session_id
        return session_id

    def prompt(self, text: str, *, session_id: str | None = None,
               timeout: float = 600.0) -> Turn:
        """Send one prompt and return what the whole turn amounted to."""
        target = session_id or self.session_id
        if not target:
            raise ValueError("open a session before prompting")
        collector, finished = TurnCollector(target), threading.Event()
        with self._lock:
            self._turns[target] = (collector, finished)
        try:
            result = self._call(
                "session/prompt",
                {"sessionId": target,
                 "prompt": [{"type": "text", "text": text}]}, timeout=timeout)
            reason = result.get("stopReason") if isinstance(result, dict) else None
            if isinstance(reason, str) and reason:
                collector.turn.stop_reason = reason  # protocol version 1
            elif not finished.wait(timeout):
                raise TimeoutError(f"the turn did not end within {timeout:g}s")
        finally:
            with self._lock:
                self._turns.pop(target, None)
        return collector.turn

    def cancel(self, session_id: str | None = None) -> None:
        """Ask the agent to stop. It still ends the turn with a stop reason."""
        self._conn.notify("session/cancel",
                          {"sessionId": session_id or self.session_id})

    def close(self, *, timeout: float = 5.0) -> None:
        self._conn.close()
        process = self.process
        if process is None:
            return
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout)

    @property
    def stderr(self) -> str:
        """Whatever the agent wrote to stderr, which is where its faults land."""
        return b"".join(self._stderr).decode("utf-8", "replace")

    # -- internals -----------------------------------------------------------

    def _call(self, method: str, params: object, *, timeout: float) -> dict:
        try:
            result = self._conn.call(method, params, timeout=timeout)
        except PeerError as exc:
            if exc.code == AUTH_REQUIRED:
                raise AuthRequired(
                    f"{method} needs the operator to sign in to this agent: "
                    f"{exc.message}") from exc
            raise
        return result if isinstance(result, dict) else {}

    def _deliver(self, params: dict) -> None:
        session_id = params.get("sessionId")
        with self._lock:
            armed = self._turns.get(session_id if isinstance(session_id, str)
                                    else "")
        if armed is None:
            # An update outside any turn we are waiting on. Kept, not dropped:
            # it is still part of the record of what the agent did.
            self.stray_updates.append(params)
            return
        collector, finished = armed
        if collector.accept(params):
            finished.set()
