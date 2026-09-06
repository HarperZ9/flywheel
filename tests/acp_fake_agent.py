"""A hand-written ACP agent for testing the client against.

Written with json.dumps and a raw pipe rather than on top of harness.acp_wire,
so a framing mistake shared by both halves shows up as a failing test instead of
cancelling itself out. It answers the methods a client calls and can call back
into the client the way a real agent does.
"""
from __future__ import annotations

import json
import os
import threading

from harness.acp_client import AcpClient
from harness.acp_connection import Connection


def default_prompt(agent, session_id, prompt):
    """One thought, one message, one clean stop."""
    agent.update(session_id, sessionUpdate="agent_thought",
                 content={"type": "text", "text": "thinking"})
    agent.update(session_id, sessionUpdate="agent_message_chunk",
                 content={"type": "text", "text": "done: " + text_of(prompt)})
    return "end_turn"


def text_of(prompt):
    return "".join(block.get("text", "") for block in prompt
                   if isinstance(block, dict))


class FakeAgent:
    """Serves one ACP connection over a pair of byte streams."""

    def __init__(self, *, version: int = 2, on_prompt=default_prompt,
                 strict: bool = True, respond_first: bool = False,
                 session_id: str = "sess-1") -> None:
        self.version = version
        self.on_prompt = on_prompt
        self.strict = strict
        self.respond_first = respond_first
        self.session_id = session_id
        self.received: list[dict] = []
        self.initialize_params: dict = {}
        self.cancelled = threading.Event()
        self._ids = iter(range(10_000, 20_000))
        self._pending: dict[int, threading.Event] = {}
        self._answers: dict[int, dict] = {}
        self._write_lock = threading.Lock()
        self._out = None
        self._in = None

    # -- transport -----------------------------------------------------------

    def serve(self, incoming, outgoing) -> None:
        self._in, self._out = incoming, outgoing
        for line in iter(incoming.readline, b""):
            if not line.strip():
                continue
            message = json.loads(line.decode("utf-8"))
            self.received.append(message)
            if "method" in message:
                threading.Thread(target=self._dispatch, args=(message,),
                                 daemon=True).start()
            else:
                self._settle(message)

    def _write(self, message: dict) -> None:
        with self._write_lock:
            self._out.write(
                (json.dumps(message) + "\n").encode("utf-8"))
            self._out.flush()

    def update(self, session_id: str, **update) -> None:
        self._write({"jsonrpc": "2.0", "method": "session/update",
                     "params": {"sessionId": session_id, "update": update}})

    def call(self, method: str, params: dict, timeout: float = 5.0) -> dict:
        """Call the client and wait, the way an agent asks for permission."""
        call_id = next(self._ids)
        done = threading.Event()
        self._pending[call_id] = done
        self._write({"jsonrpc": "2.0", "id": call_id, "method": method,
                     "params": params})
        if not done.wait(timeout):
            raise TimeoutError(method)
        return self._answers.pop(call_id)

    def _settle(self, message: dict) -> None:
        done = self._pending.pop(message.get("id"), None)
        if done is not None:
            self._answers[message["id"]] = message
            done.set()

    # -- methods -------------------------------------------------------------

    def _dispatch(self, message: dict) -> None:
        method, params = message["method"], message.get("params") or {}
        if "id" not in message:
            if method == "session/cancel":
                self.cancelled.set()
            return
        try:
            result = self._answer(method, params, message["id"])
        except _Refuse as refusal:
            self._write({"jsonrpc": "2.0", "id": message["id"],
                         "error": {"code": refusal.code,
                                   "message": refusal.text}})
            return
        if result is not _ALREADY_SENT:
            self._write({"jsonrpc": "2.0", "id": message["id"],
                         "result": result})

    def _answer(self, method: str, params: dict, call_id):
        if method == "initialize":
            return self._initialize(params)
        if method == "session/new":
            return {"sessionId": self.session_id}
        if method == "session/prompt":
            return self._prompt(params, call_id)
        raise _Refuse(-32601, method)

    def _initialize(self, params: dict) -> dict:
        if self.version == 1 and self.strict and "capabilities" in params:
            raise _Refuse(-32602, "this agent speaks version 1")
        self.initialize_params = params
        return {"protocolVersion": self.version,
                "capabilities": {"loadSession": False},
                "info": {"name": "fake", "version": "0"}}

    def _prompt(self, params: dict, call_id):
        session_id = params["sessionId"]
        if self.respond_first and self.version == 2:
            # The idle update can land before the prompt response does. Sending
            # the response first makes the client take that path.
            self._write({"jsonrpc": "2.0", "id": call_id, "result": {}})
        reason = self.on_prompt(self, session_id, params.get("prompt") or [])
        if self.version == 1:
            return {"stopReason": reason}
        self.update(session_id, sessionUpdate="state_update", state="idle",
                    stopReason=reason)
        if self.respond_first:
            return _ALREADY_SENT
        return {}


class _Refuse(Exception):
    def __init__(self, code: int, text: str) -> None:
        super().__init__(text)
        self.code, self.text = code, text


_ALREADY_SENT = object()


def _pipe():
    read_fd, write_fd = os.pipe()
    return os.fdopen(read_fd, "rb", 0), os.fdopen(write_fd, "wb", 0)


def connect(agent: FakeAgent, **client_kwargs):
    """Wire one FakeAgent to one AcpClient over two pipes. Returns the client."""
    to_agent_read, to_agent_write = _pipe()
    to_client_read, to_client_write = _pipe()
    threading.Thread(target=agent.serve, args=(to_agent_read, to_client_write),
                     name="fake-agent", daemon=True).start()
    connection = Connection(to_agent_write, to_client_read,
                            observer=client_kwargs.pop("observer", None))
    client = AcpClient(connection, **client_kwargs)
    connection.start()
    return client
