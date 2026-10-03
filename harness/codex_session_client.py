"""Typed Codex app-server session client.

The client only shapes protocol methods. It does not launch Codex, read account
state, or make authorization decisions.
"""
from __future__ import annotations

from typing import Any, Protocol


class CodexSessionTransport(Protocol):
    def request(self, method: str, params: Any = None, *,
                timeout: float | None = None) -> Any: ...
    def notify(self, method: str, params: Any = None) -> None: ...


class CodexSessionClient:
    def __init__(self, transport: CodexSessionTransport):
        self.transport = transport
        self.initialize_response: dict | None = None

    def initialize(
            self, *, name: str = "flywheel", title: str = "Flywheel",
            version: str = "1.0.0",
            capabilities: dict | None = None) -> dict:
        params = {
            "clientInfo": {"name": name, "title": title, "version": version},
            "capabilities": dict(capabilities or {}),
        }
        response = self.transport.request("initialize", params)
        self.initialize_response = response
        self.transport.notify("initialized")
        return response

    def thread_start(self, **params) -> Any:
        return self.transport.request("thread/start", _clean(params))

    def thread_resume(self, thread_id: str, **params) -> Any:
        _reject_collisions(params, {"threadId"})
        payload = {"threadId": _required("threadId", thread_id)}
        payload.update(_clean(params))
        return self.transport.request("thread/resume", payload)

    def thread_read(self, thread_id: str, *, include_turns: bool | None = None) -> Any:
        params = {"threadId": _required("threadId", thread_id)}
        if include_turns is not None:
            params["includeTurns"] = include_turns
        return self.transport.request("thread/read", params)

    def thread_list(
            self, *, cursor: str | None = None, limit: int | None = None,
            archived: bool | None = None, cwd: str | None = None,
            search_term: str | None = None) -> Any:
        return self.transport.request("thread/list", _clean({
            "cursor": cursor, "limit": limit, "archived": archived,
            "cwd": cwd, "searchTerm": search_term,
        }))

    def thread_unsubscribe(self, thread_id: str) -> Any:
        return self.transport.request(
            "thread/unsubscribe", {"threadId": _required("threadId", thread_id)})

    def turn_start(
            self, thread_id: str, input: list | dict, *,
            client_user_message_id: str | None = None, **params) -> Any:
        _reject_collisions(params, {"threadId", "input", "clientUserMessageId"})
        payload = {
            "threadId": _required("threadId", thread_id),
            "input": input,
        }
        if client_user_message_id is not None:
            payload["clientUserMessageId"] = client_user_message_id
        payload.update(_clean(params))
        return self.transport.request("turn/start", payload)

    def turn_steer(
            self, thread_id: str, expected_turn_id: str, input: list | dict, *,
            client_user_message_id: str | None = None) -> Any:
        payload = {
            "threadId": _required("threadId", thread_id),
            "expectedTurnId": _required("expectedTurnId", expected_turn_id),
            "input": input,
        }
        if client_user_message_id is not None:
            payload["clientUserMessageId"] = client_user_message_id
        return self.transport.request("turn/steer", payload)

    def turn_interrupt(self, thread_id: str, turn_id: str) -> Any:
        return self.transport.request("turn/interrupt", {
            "threadId": _required("threadId", thread_id),
            "turnId": _required("turnId", turn_id),
        })

    def model_list(
            self, *, cursor: str | None = None, limit: int | None = None,
            include_hidden: bool | None = None) -> Any:
        return self.transport.request("model/list", _clean({
            "cursor": cursor, "limit": limit, "includeHidden": include_hidden,
        }))

    def config_read(
            self, *, cwd: str | None = None,
            include_layers: bool | None = None) -> Any:
        return self.transport.request("config/read", _clean({
            "cwd": cwd, "includeLayers": include_layers,
        }))

    def config_requirements_read(self) -> Any:
        return self.transport.request("configRequirements/read")

    def mcp_server_status_list(
            self, *, thread_id: str | None = None,
            detail: str | None = None, cursor: str | None = None,
            limit: int | None = None) -> Any:
        return self.transport.request("mcpServerStatus/list", _clean({
            "threadId": thread_id, "detail": detail,
            "cursor": cursor, "limit": limit,
        }))

    def mcp_server_tool_call(
            self, thread_id: str, server: str, tool: str, *,
            arguments: dict | None = None, meta: dict | None = None) -> Any:
        return self.transport.request("mcpServer/tool/call", _clean({
            "threadId": _required("threadId", thread_id),
            "server": _required("server", server),
            "tool": _required("tool", tool),
            "arguments": arguments,
            "_meta": meta,
        }))


def _clean(params: dict) -> dict:
    return {key: value for key, value in params.items() if value is not None}


def _reject_collisions(params: dict, reserved: set[str]) -> None:
    collisions = reserved.intersection(params)
    if collisions:
        raise ValueError(sorted(collisions)[0])


def _required(name: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(name)
    return value
