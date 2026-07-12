"""mcp_client.py — a zero-dependency MCP client (JSON-RPC 2.0 over stdio).

Flywheel already EXPOSES an MCP server (local_mcp.py). This lets it CONSUME the
rest of the ecosystem: the gated agent loop can call out to any MCP tool server
(filesystem, search, database, a sibling flagship), and every external call and
its result is witnessed in the same hash-chained session ledger as a built-in
tool. Table stakes now across Cursor / Cline / Claude Code / Windsurf, and Flywheel
adds the part they lack: the outbound call is gated (opt-in) and re-checkable.

Standard library only (subprocess + threading + queue + json). Transport is
injectable, so the handshake / list / call logic is falsifiable without spawning
a server. MCP stdio framing is newline-delimited JSON (one message per line).
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading

PROTOCOL_VERSION = "2025-06-18"
_EOF = object()


class MCPError(RuntimeError):
    """An MCP server returned an error, closed, or timed out."""


class StdioTransport:
    """Newline-delimited JSON-RPC over a subprocess's stdin/stdout. A background
    reader thread makes receive() timeout-safe cross-platform (no select on pipes)."""

    def __init__(self, command: list, *, timeout: float = 30.0):
        self.timeout = timeout
        self.proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._q: "queue.Queue" = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            for line in self.proc.stdout:                # blocks in the thread, not the caller
                line = line.strip()
                if not line:
                    continue
                try:
                    self._q.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        finally:
            self._q.put(_EOF)

    def send(self, msg: dict) -> None:
        if self.proc.stdin is None:
            raise MCPError("server stdin is closed")
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def receive(self) -> dict:
        try:
            item = self._q.get(timeout=self.timeout)
        except queue.Empty:
            raise MCPError(f"no response within {self.timeout}s") from None
        if item is _EOF:
            raise MCPError("server closed the connection")
        return item

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class MCPClient:
    """Drive an MCP server: initialize, list tools, call a tool. Pass `command`
    to spawn a server over stdio, or inject `transport` (e.g. a fake) for tests."""

    def __init__(self, command: "list | None" = None, *, transport=None,
                 timeout: float = 30.0, client_name: str = "flywheel"):
        if transport is None and command is None:
            raise ValueError("MCPClient needs a command or a transport")
        self._t = transport if transport is not None else StdioTransport(command, timeout=timeout)
        self._id = 0
        self.client_name = client_name
        self.server_info: dict = {}
        self.tools: list = []
        self.started = False

    def _request(self, method: str, params: "dict | None" = None) -> dict:
        self._id += 1
        rid = self._id
        self._t.send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
        while True:                                      # skip server-initiated notifications
            msg = self._t.receive()
            if msg.get("id") != rid:
                continue
            if "error" in msg:
                raise MCPError(f"{method}: {msg['error']}")
            return msg.get("result", {})

    def _notify(self, method: str, params: "dict | None" = None) -> None:
        self._t.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def start(self) -> "MCPClient":
        res = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": self.client_name, "version": "1"}})
        self.server_info = res.get("serverInfo", {})
        self._notify("notifications/initialized")
        self.started = True
        return self

    def list_tools(self) -> list:
        self.tools = self._request("tools/list").get("tools", [])
        return self.tools

    def call_tool(self, name: str, arguments: "dict | None" = None) -> dict:
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})

    def call_text(self, name: str, arguments: "dict | None" = None) -> dict:
        """Flatten a tools/call result to {ok, text, raw}. isError -> ok False."""
        res = self.call_tool(name, arguments)
        parts = [c.get("text", "") for c in res.get("content", [])
                 if isinstance(c, dict) and c.get("type") == "text"]
        return {"ok": not res.get("isError", False), "text": "\n".join(parts), "raw": res}

    def close(self) -> None:
        try:
            self._t.close()
        except Exception:
            pass

    def __enter__(self) -> "MCPClient":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


def as_external_tools(client: MCPClient, *, prefix: str = "") -> dict:
    """Turn an MCPClient's discovered tools into ToolExecutor `external` entries.
    Each entry is {fn, description}; fn(args) -> (ok, text). The executor gates
    them behind allow_mcp and the loop witnesses each call like any tool."""
    tools = client.tools or client.list_tools()
    out = {}
    for t in tools:
        tool_name = t.get("name", "")
        if not tool_name:
            continue

        def _make(tn):
            def fn(args):
                r = client.call_text(tn, args if isinstance(args, dict) else {})
                return r["ok"], r["text"]
            return fn

        out[(prefix + tool_name) if prefix else tool_name] = {
            "fn": _make(tool_name), "description": t.get("description", "")}
    return out
