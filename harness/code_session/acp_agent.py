"""acp_agent.py -- `flywheel code --acp`: Flywheel as an Agent Client Protocol agent.

An editor that speaks ACP (Zed, JetBrains, VS Code through an ACP extension)
starts `flywheel code --acp` and talks JSON-RPC over its stdin and stdout. Each
`session/new` opens a coding session in the editor's folder; each
`session/prompt` runs one turn of the same gated loop `flywheel code` runs, and
streams it back as `session/update` notifications: the model's words as
`agent_message_chunk`, every tool call as a `tool_call` and its outcome as a
`tool_call_update`. A call the permission mode would ask about is put to the
editor with `session/request_permission`; its answer decides, and the decision
lands on the session's ledger like any other. `session/cancel` stops the turn
at the next model call or tool call and the prompt answers `cancelled`.

Written against ACP schema v1.25.0 (protocol version 1). The editor's own MCP
server list in `session/new` is not started yet; the session's configured
servers are.
"""
from __future__ import annotations

import itertools
import sys
import threading
import time

from harness.acp_turn import text_of
from harness.acp_wire import AcpFraming
from harness.jsonrpc_peer import InvalidParams, MethodNotFound, Peer
from harness.local_tools import ToolResult

PROTOCOL_VERSION = 1
KIND = {"read_file": "read", "list_dir": "read", "repo_map": "read", "skill": "read",
        "grep": "search", "glob": "search", "write_file": "edit", "edit_file": "edit",
        "apply_patch": "edit", "run": "execute", "web_fetch": "fetch", "todo": "think"}
OPTIONS = [{"optionId": "allow", "name": "Allow", "kind": "allow_once"},
           {"optionId": "always", "name": "Always allow", "kind": "allow_always"},
           {"optionId": "reject", "name": "Reject", "kind": "reject_once"}]
ANSWERS = {"allow": "yes", "always": "always"}


class Cancelled(Exception):
    """The editor sent session/cancel for the running turn."""


def _visible(text: str) -> str:
    """Model text without the TOOL protocol lines, which the editor sees as tool calls."""
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("TOOL ")).strip()


class _Live:
    """One editor session wrapped around a CodeSession."""

    def __init__(self, sid: str, session, peer):
        self.sid, self.session, self.peer = sid, session, peer
        self.cancelled = threading.Event()
        self.current = ""
        self._ids = itertools.count(1)
        self._wrap()

    def update(self, body: dict) -> None:
        self.peer.notify("session/update", {"sessionId": self.sid, "update": body})

    def approve(self, name: str, args: dict) -> str:
        reply = self.peer.call("session/request_permission", {
            "sessionId": self.sid, "options": OPTIONS,
            "toolCall": {"toolCallId": self.current, "title": f"{name}",
                         "kind": KIND.get(name, "other"), "status": "pending",
                         "rawInput": args}})
        outcome = (reply or {}).get("outcome") or {}
        if outcome.get("outcome") != "selected":
            return "no"
        return ANSWERS.get(outcome.get("optionId"), "no")

    def _wrap(self) -> None:
        executor, agent = self.session.executor, self.session.agent
        run_tool, send = executor.execute, agent.send

        def execute(name, args, rationale=None):
            if self.cancelled.is_set():
                return ToolResult(name, args, False, "[cancelled] the turn was cancelled")
            self.current = f"call_{next(self._ids)}"
            self.update({"sessionUpdate": "tool_call", "toolCallId": self.current,
                         "title": name, "kind": KIND.get(name, "other"),
                         "status": "in_progress", "rawInput": args})
            result = run_tool(name, args, rationale=rationale)
            self.update({"sessionUpdate": "tool_call_update", "toolCallId": self.current,
                         "status": "completed" if result.ok else "failed",
                         "content": [{"type": "content", "content": {
                             "type": "text", "text": result.output[:4000]}}]})
            return result

        def guarded_send(text):
            if self.cancelled.is_set():
                raise Cancelled()
            return send(text)

        executor.execute, agent.send = execute, guarded_send
        executor.approver = self.approve
        self.session.on_event = self._on_event

    def _on_event(self, event: dict) -> None:
        if event.get("type") == "assistant":
            text = _visible(event.get("text") or "")
            if text:
                self.update({"sessionUpdate": "agent_message_chunk",
                             "content": {"type": "text", "text": text + "\n"}})

    def prompt(self, blocks) -> dict:
        self.cancelled.clear()
        text = text_of(blocks).strip()
        if not text:
            raise InvalidParams("prompt has no text")
        try:
            result = self.session.turn(text)
        except Cancelled:
            return {"stopReason": "cancelled"}
        if self.cancelled.is_set():
            return {"stopReason": "cancelled"}
        if result.final.startswith("[max_steps reached"):
            return {"stopReason": "max_turn_requests"}
        return {"stopReason": "end_turn"}


class AcpAgent:
    """The JSON-RPC handler. `make_session(cwd)` builds a CodeSession for a folder."""

    def __init__(self, make_session):
        self.make_session = make_session
        self.peer = None
        self.sessions: dict = {}
        self._ids = itertools.count(1)

    def on_request(self, method: str, params: dict):
        if method == "initialize":
            return {"protocolVersion": PROTOCOL_VERSION,
                    "agentCapabilities": {"loadSession": False, "promptCapabilities": {
                        "image": False, "audio": False, "embeddedContext": False}},
                    "authMethods": []}
        if method == "session/new":
            cwd = params.get("cwd")
            if not isinstance(cwd, str) or not cwd:
                raise InvalidParams("session/new needs an absolute cwd")
            sid = f"fw_{next(self._ids)}"
            self.sessions[sid] = _Live(sid, self.make_session(cwd), self.peer)
            return {"sessionId": sid}
        if method == "session/prompt":
            live = self.sessions.get(params.get("sessionId"))
            if live is None:
                raise InvalidParams("unknown sessionId")
            return live.prompt(params.get("prompt") or [])
        raise MethodNotFound(method)

    def on_notification(self, method: str, params: dict) -> None:
        if method == "session/cancel":
            live = self.sessions.get(params.get("sessionId"))
            if live is not None:
                live.cancelled.set()

    def close(self) -> None:
        for live in self.sessions.values():
            live.session.close()


def serve(make_session, stdin=None, stdout=None) -> int:
    """Run until the editor closes the stream."""
    agent = AcpAgent(make_session)
    peer = Peer(stdout or sys.stdout.buffer, stdin or sys.stdin.buffer,
                framing=AcpFraming(), handler=agent, name="flywheel-acp")
    agent.peer = peer
    peer.start()
    try:
        while not peer.closed:
            time.sleep(0.2)
    finally:
        agent.close()
    return 0
