"""A stdio MCP server with background runs, for the lane session tests.

It answers the relay run tools the way relay does: ``local_agent_start`` starts
a run in a thread and returns its id at once; ``local_agent_status`` and
``local_agent_result`` read the run from this process's memory, so a fresh
process answers "unknown run_id". The run finishes after ``FAKE_RUN_SECONDS``
(default 0.2) unless its goal is "hold", which runs until the process ends.

It writes one line per start of this process to ``FAKE_PID_LOG`` (its pid) and
one JSON line per tool call to ``FAKE_CALL_LOG``, so a test can count children
and read the arguments a call delivered. It exits when stdin reaches EOF, the
way relay's and index's serve loops do.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

RUNS: dict[str, dict] = {}
_LOCK = threading.Lock()
TOOLS = ("local_agent_start", "local_agent_status", "local_agent_result",
         "local_agent_runs", "local_agent_run", "relay.status")


def _log(env_name: str, line: str) -> None:
    path = os.environ.get(env_name)
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def _finish(run_id: str, seconds: float) -> None:
    time.sleep(seconds)
    with _LOCK:
        RUNS[run_id]["state"] = "done"


def _call(name: str, args: dict) -> dict:
    _log("FAKE_CALL_LOG", json.dumps({"tool": name, "args": args, "pid": os.getpid()}))
    if name == "local_agent_start":
        run_id = f"r{len(RUNS) + 1}x{os.getpid()}"
        with _LOCK:
            RUNS[run_id] = {"state": "running", "goal": args.get("goal")}
        if args.get("goal") != "hold":
            seconds = float(os.environ.get("FAKE_RUN_SECONDS", "0.2"))
            threading.Thread(target=_finish, args=(run_id, seconds), daemon=True).start()
        return {"run_id": run_id, "state": "running"}
    if name in ("local_agent_status", "local_agent_result"):
        run = RUNS.get(str(args.get("run_id")))
        if run is None:
            return {"error": f"unknown run_id {args.get('run_id')!r}"}
        out = {"run_id": args["run_id"], "state": run["state"]}
        if name == "local_agent_result" and run["state"] == "done":
            out["result"] = {"final": f"did {run['goal']}"}
        return out
    if name == "local_agent_runs":
        return {"runs": [{"run_id": k, **v} for k, v in RUNS.items()]}
    return {"ok": True, "pid": os.getpid()}


def _handle(req: dict) -> dict | None:
    rid, method = req.get("id"), req.get("method")
    if rid is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {},
                  "serverInfo": {"name": "fake-session", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "inputSchema": {"type": "object"}} for n in TOOLS]}
    elif method == "tools/call":
        params = req.get("params") or {}
        body = _call(params.get("name"), params.get("arguments") or {})
        result = {"content": [{"type": "text", "text": json.dumps(body)}]}
    else:
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": method}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def main() -> int:
    _log("FAKE_PID_LOG", str(os.getpid()))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        resp = _handle(json.loads(line))
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
