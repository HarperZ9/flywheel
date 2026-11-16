"""mcp_call.py: call one tool on one stdio MCP server, then stop the server.

  python -m plexus.runner.mcp_call SPEC.json

SPEC holds {"launch": [argv], "cwd": str|null, "tool": name, "args": {...},
"timeout_s": float}. fanout runs this module under plexus.budget, so the
server inherits the same time and memory limit. The tool's result goes to
stdout as JSON. Exit 0: the tool answered; 3: it answered with isError;
2: the server could not be reached or broke the protocol.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time

PROTOCOL = "2025-06-18"


def _reader(stream, q):
    for line in iter(stream.readline, b""):
        q.put(line)
    q.put(None)


def call(spec: dict) -> "tuple[int, dict]":
    deadline = time.monotonic() + float(spec.get("timeout_s", 30))
    proc = subprocess.Popen(spec["launch"], cwd=spec.get("cwd") or None, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=sys.stderr.buffer if hasattr(sys.stderr, "buffer") else None)
    q: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, q), daemon=True).start()

    def send(msg):
        proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def wait_for(rid):
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"no answer to request {rid} in time")
            line = q.get(timeout=left)
            if line is None:
                raise ConnectionError("server closed its output")
            try:
                msg = json.loads(line)
            except ValueError:
                continue                              # a server printing logs on stdout
            if isinstance(msg, dict) and msg.get("id") == rid:
                if "error" in msg:
                    raise ConnectionError(f"server error: {msg['error']}")
                return msg.get("result", {})

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": PROTOCOL, "capabilities": {},
                         "clientInfo": {"name": "plexus-fanout", "version": "1"}}})
        info = wait_for(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": spec["tool"], "arguments": spec.get("args", {})}})
        result = wait_for(2)
        return (3 if result.get("isError") else 0), {"server": info.get("serverInfo", {}), "result": result}
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=3)
        except Exception:                             # the server would not stop: end it
            proc.kill()


def main(argv: "list[str]") -> int:
    with open(argv[0], encoding="utf-8") as f:
        spec = json.load(f)
    try:
        code, out = call(spec)
    except (OSError, TimeoutError, ConnectionError, queue.Empty) as e:
        print(f"mcp_call: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
