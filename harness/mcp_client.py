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

import collections
import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass

PROTOCOL_VERSION = "2025-06-18"
_EOF = object()


@dataclass(frozen=True)
class LaunchSpec:
    argv: tuple[str, ...]
    cwd: str | None = None
    env_overrides: tuple[tuple[str, str], ...] = ()
    inherit_env: bool = True
    url: str = ""                   # set instead of argv for a lane that is already
    #                                 running behind an endpoint rather than spawned


class MCPError(RuntimeError):
    """An MCP server returned an error, closed, or timed out."""


class StdioTransport:
    """Newline-delimited JSON-RPC over a subprocess's stdin/stdout. A background
    reader thread makes receive() timeout-safe cross-platform (no select on pipes)."""

    def __init__(self, command: "list | LaunchSpec", *, timeout: float = 30.0):
        self.timeout = timeout
        popen_kwargs = {
            "stdin": subprocess.PIPE, "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE, "text": True, "bufsize": 1}
        if isinstance(command, LaunchSpec):
            child_env = os.environ.copy() if command.inherit_env else {}
            child_env.update(command.env_overrides)
            argv = list(command.argv)
            popen_kwargs.update(cwd=command.cwd, env=child_env)
        else:
            argv = command
        self.proc = subprocess.Popen(
            argv, **popen_kwargs)
        self._q: "queue.Queue" = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # A server that dies on launch says why on stderr; discarding it turns
        # a one-line ModuleNotFoundError into a bare "closed the connection".
        # Keep a bounded tail of the server's own words for the error report.
        self._err_tail: "collections.deque" = collections.deque(maxlen=30)
        self._err_reader = threading.Thread(target=self._err_loop, daemon=True)
        self._err_reader.start()

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

    def _err_loop(self) -> None:
        try:
            for line in self.proc.stderr:
                line = line.rstrip()
                if line:
                    self._err_tail.append(line)
        except (ValueError, OSError):
            pass

    def stderr_tail(self) -> str:
        """The last stderr lines the server wrote (joined), or ''. After the
        process exits, briefly joins the reader so the tail is complete."""
        if self.proc.poll() is not None:
            self._err_reader.join(timeout=0.5)
        return "\n".join(self._err_tail).strip()

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
            if os.name == "nt":
                # terminate() kills only the direct child. A pip-installed
                # server runs shim -> real interpreter, so the grandchild
                # survives and orphans pile up one per timed-out call.
                # taskkill /T takes the whole tree.
                subprocess.run(
                    ["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                    capture_output=True, timeout=10)
            else:
                self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class MCPClient:
    """Drive an MCP server: initialize, list tools, call a tool. Pass `command`
    to spawn a server over stdio, a LaunchSpec carrying a url to reach one over
    HTTP, or inject `transport` (e.g. a fake) for tests."""

    def __init__(self, command: "list | LaunchSpec | None" = None, *, transport=None,
                 timeout: float = 30.0, client_name: str = "flywheel"):
        if transport is None and command is None:
            raise ValueError("MCPClient needs a command or a transport")
        if transport is None:
            spec_url = getattr(command, "url", "")
            # A spec carrying a url, or one with no argv to spawn, is a lane that is
            # already running behind an endpoint. Lazy import: mcp_http imports MCPError.
            if spec_url or not getattr(command, "argv", ("stdio",)):
                from .mcp_http import HttpTransport
                transport = HttpTransport(spec_url, timeout=timeout)
            else:
                transport = StdioTransport(command, timeout=timeout)
        self._t = transport
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
        if self.started:
            return self
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

    def stderr_tail(self) -> str:
        """The server's own last words on stderr, or '' (fakes may lack it)."""
        fn = getattr(self._t, "stderr_tail", None)
        try:
            return fn() if callable(fn) else ""
        except Exception:
            return ""

    def close(self) -> None:
        try:
            self._t.close()
        except Exception:
            pass

    def __enter__(self) -> "MCPClient":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


class MCPAllowlist:
    """Only permit spawning MCP servers whose command matches an allowlisted argv
    prefix. A web route must never launch an arbitrary subprocess; this is the gate
    the HTTP surface consults before open_mcp(). An empty allowlist denies all."""

    def __init__(self, allowed: "list | None" = None):
        self.allowed = [list(entry) for entry in (allowed or []) if entry]

    def permits(self, command: list) -> bool:
        cmd = list(command)
        return any(cmd[:len(entry)] == entry for entry in self.allowed)

    def check(self, command: list) -> None:
        if not self.permits(command):
            raise MCPError(f"MCP server not allowlisted: {list(command)[:3]}")


def open_mcp(command: list, *, allowlist: MCPAllowlist, timeout: float = 30.0,
             client_name: str = "flywheel") -> MCPClient:
    """The ONLY sanctioned way to spawn an MCP server from an untrusted caller:
    the command is checked against the allowlist before any subprocess starts."""
    allowlist.check(command)
    return MCPClient(command, timeout=timeout, client_name=client_name).start()


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
