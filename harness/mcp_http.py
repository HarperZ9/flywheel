"""mcp_http.py — MCP over Streamable HTTP, for a lane that lives on the web.

Every lane before this one is a subprocess: flywheel spawns it, speaks
newline-delimited JSON-RPC over its stdin and stdout, and kills it afterwards.
A board that agents reach over the open web cannot be spawned. It is already
running, somewhere else, behind a URL.

This is the same JSON-RPC conversation over one POST per message, which is what
the MCP Streamable HTTP transport specifies. `MCPClient` takes an injected
transport, so nothing in the client, the lane probe, or the tool bridge has to
know which of the two it got. The duck type is send / receive / close.

A POST carrying a request comes back with that request's response, and a POST
carrying a notification comes back 202 with no body. So `send` performs the
call and queues whatever came back, and `receive` pops it. A notification
queues nothing, which is correct: the caller that sent one never asks.

Standard library only (urllib), matching the stdio transport beside it.
"""
from __future__ import annotations

import json
import queue
import urllib.error
import urllib.request

from .mcp_client import MCPError

# Both are named because the transport permits a server to answer either way,
# and a server that only ever sends one still sees the other offered.
_ACCEPT = "application/json, text/event-stream"


def _sse_messages(body: str) -> list:
    """Pull the JSON payloads out of an event stream. A `data:` line per message."""
    out = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        try:
            out.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return out


class HttpTransport:
    """One POST per message to an MCP endpoint. Speaks the transport `MCPClient`
    consumes, so an http lane and a stdio lane are the same object downstream."""

    def __init__(self, url: str, *, timeout: float = 30.0, headers: "dict | None" = None):
        if not url:
            raise MCPError("no endpoint configured for this lane")
        if not url.startswith(("http://", "https://")):
            raise MCPError(f"not an http(s) MCP endpoint: {url!r}")
        self.url = url
        self.timeout = timeout
        self.session_id: str | None = None
        self._headers = dict(headers or {})
        self._q: "queue.Queue" = queue.Queue()
        self._last_status: int | None = None

    def _request_headers(self) -> dict:
        head = {"content-type": "application/json", "accept": _ACCEPT,
                "mcp-protocol-version": "2025-06-18", **self._headers}
        if self.session_id:
            # The server may hand out a session on initialize and expect it back
            # on everything after. A server that does not is unaffected.
            head["mcp-session-id"] = self.session_id
        return head

    def send(self, msg: dict) -> None:
        body = json.dumps(msg).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers=self._request_headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self._absorb(resp.status, resp.headers, resp.read())
        except urllib.error.HTTPError as e:
            # A JSON-RPC error is a valid answer carried on a 4xx. Reading it
            # turns "HTTP 400" into the server's own sentence about what it
            # refused, which is the difference between a bug report and a shrug.
            self._absorb(e.code, e.headers, e.read())
        except urllib.error.URLError as e:
            raise MCPError(f"{self.url}: {e.reason}") from None
        except OSError as e:
            raise MCPError(f"{self.url}: {e}") from None

    def _absorb(self, status: int, headers, raw: bytes) -> None:
        self._last_status = status
        session = headers.get("mcp-session-id") if headers else None
        if session:
            self.session_id = session
        if not raw:
            return                                       # 202 for a notification
        kind = (headers.get("content-type", "") if headers else "").lower()
        if "text/event-stream" in kind:
            for message in _sse_messages(raw.decode("utf-8", "replace")):
                self._q.put(message)
            return
        try:
            parsed = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            raise MCPError(
                f"{self.url}: HTTP {status} body is not JSON: "
                f"{raw[:120].decode('utf-8', 'replace')!r}") from None
        for message in (parsed if isinstance(parsed, list) else [parsed]):
            self._q.put(message)

    def receive(self) -> dict:
        try:
            return self._q.get_nowait()
        except queue.Empty:
            raise MCPError(
                f"{self.url}: HTTP {self._last_status} carried no JSON-RPC reply") from None

    def stderr_tail(self) -> str:
        """A remote server writes to its own logs, not to a pipe we hold."""
        return ""

    def close(self) -> None:
        """Nothing to reap. There is no child process on this side of the wire."""
        return None
