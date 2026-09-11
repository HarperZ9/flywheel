"""Run bounded MCP fixture probes against built Node lane payloads."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from node_lane_payload_lib import PayloadError, load_jsonl, minimal_env

MANIFEST = Path("packaging/node-lane-payloads.jsonl")


def _fixtures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        entry = row["entrypoint"]
        out.append({
            "lane": row["lane"],
            "server_info": entry["server_info"],
            "status_tool": entry["status_tool"],
            "doctor_tool": entry["doctor_tool"],
            "workflow": "initialize -> tools/list -> status -> doctor",
            "network": "none",
            "device_ui_browser_provider": "none",
        })
    return out


def _request(proc: subprocess.Popen[str], payload: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(json.dumps(payload, sort_keys=True) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        raise PayloadError("MCP process closed before response")
    response = json.loads(line)
    if "error" in response:
        raise PayloadError(str(response["error"]))
    return response


def _tool_text(response: dict[str, Any]) -> str:
    result = response.get("result") or {}
    content = result.get("content") or []
    if content and isinstance(content[0], dict):
        return str(content[0].get("text", ""))
    return json.dumps(result, sort_keys=True)


def _run_lane(payload_root: Path, row: dict[str, Any]) -> dict[str, Any]:
    lane = row["lane"]
    node = payload_root / "components" / "node" / "v24.21.0-win-x64" / "node.exe"
    package = payload_root / "components" / "node-lanes" / f"{lane}-{row['version']}" / "package"
    script = package / row["entrypoint"]["script"]
    if not node.exists() or not script.exists():
        raise PayloadError(f"{lane}: payload node/script missing")
    proc = subprocess.Popen(
        [str(node), str(script)],
        cwd=str(package),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=minimal_env(),
    )
    try:
        init = _request(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        server_info = init["result"]["serverInfo"]
        if server_info != row["entrypoint"]["server_info"]:
            raise PayloadError(f"{lane}: serverInfo mismatch: {server_info!r}")
        listed = _request(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listed["result"]["tools"]]
        if names != row["tools"]:
            raise PayloadError(f"{lane}: tool list mismatch")
        status = _request(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": row["entrypoint"]["status_tool"], "arguments": {}}})
        doctor = _request(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": row["entrypoint"]["doctor_tool"], "arguments": {}}})
        return {
            "lane": lane,
            "server_info": server_info,
            "tool_count": len(names),
            "status_excerpt": _tool_text(status)[:160],
            "doctor_excerpt": _tool_text(doctor)[:160],
        }
    finally:
        try:
            proc.stdin.close() if proc.stdin else None
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--payload-root")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    try:
        rows = load_jsonl(Path(args.manifest))
        if args.list:
            print(json.dumps({"schema": "flywheel.node-lane-fixtures/v1", "fixtures": _fixtures(rows)}, sort_keys=True))
            return 0
        if not args.payload_root:
            raise PayloadError("payload-root is required unless --list is used")
        results = [_run_lane(Path(args.payload_root), row) for row in rows]
        print(json.dumps({"schema": "flywheel.node-lane-fixture-run/v1", "verdict": "PASS", "results": results}, sort_keys=True))
        return 0
    except PayloadError as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
