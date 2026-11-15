#!/usr/bin/env python3
"""
warden_mcp_proxy -- stdio MCP transport membrane.

Wraps an MCP server process and calibrates JSON-RPC traffic at the transport
edge. SEAL mode calibrates request arguments and response text. GAP mode
forwards native bytes unchanged and writes a hash-only accountability journal.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import mcp_calibrate
from io_state import add_io_toggle_args, set_env_mode, transforms_enabled


DEFAULT_CONFIG_PATH = Path.home() / ".claude" / "cleanroom.json"
DEFAULT_AUDIT_PATH = Path.home() / ".claude" / ".warden-audit.jsonl"
DEFAULT_CHUNK_SIZE = 64 * 1024


class ProxyMode(Enum):
    SEAL = "seal"
    GAP = "gap"


class ProxyPhase(Enum):
    STARTING = "starting"
    RUNNING = "running"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass
class ProxyState:
    server_name: str
    mode: ProxyMode
    phase: ProxyPhase = ProxyPhase.RUNNING
    audit_path: Path = DEFAULT_AUDIT_PATH


class JsonLineSplitter:
    """Buffers arbitrary byte chunks and emits complete newline-delimited frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        if chunk:
            self._buffer.extend(chunk)
        frames: list[bytes] = []
        while True:
            try:
                idx = self._buffer.index(0x0A)
            except ValueError:
                break
            idx += 1
            frames.append(bytes(self._buffer[:idx]))
            del self._buffer[:idx]
        return frames

    def flush(self) -> bytes:
        if not self._buffer:
            return b""
        rest = bytes(self._buffer)
        self._buffer.clear()
        return rest


def load_proxy_state(
    server_name: str,
    config_path: Path = DEFAULT_CONFIG_PATH,
    audit_path: Path = DEFAULT_AUDIT_PATH,
) -> ProxyState:
    mode = ProxyMode.SEAL
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        raw_mode = (cfg.get("mcp_proxy") or {}).get(server_name)
        if raw_mode is None:
            raw_mode = (cfg.get("mcp_proxy") or {}).get("_default", "seal")
        mode = ProxyMode(str(raw_mode).strip().lower())
    except Exception:
        mode = ProxyMode.SEAL
    return ProxyState(server_name=server_name, mode=mode, audit_path=audit_path)


def transform_client_payload(raw: bytes, state: ProxyState) -> bytes:
    return _transform_payload(raw, state, "client_to_server")


def transform_server_payload(raw: bytes, state: ProxyState) -> bytes:
    return _transform_payload(raw, state, "server_to_client")


def _transform_payload(raw: bytes, state: ProxyState, direction: str) -> bytes:
    if not transforms_enabled():
        return raw
    if state.mode is ProxyMode.GAP:
        _write_gap_journal(state, direction, raw)
        return raw

    message = _parse_json_line(raw)
    if not isinstance(message, dict):
        return raw

    if direction == "client_to_server":
        calibrated = mcp_calibrate.calibrate_jsonrpc_request(message)
    else:
        calibrated = mcp_calibrate.calibrate_jsonrpc_response(message)
    return _serialize_json_line(calibrated, newline=raw.endswith(b"\n"))


def _parse_json_line(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
        return json.loads(text.strip())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _serialize_json_line(message: dict, newline: bool) -> bytes:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def _write_gap_journal(state: ProxyState, direction: str, raw: bytes) -> None:
    state.audit_path.parent.mkdir(parents=True, exist_ok=True)
    parsed = _parse_json_line(raw)
    method = parsed.get("method") if isinstance(parsed, dict) else None
    msg_id = parsed.get("id") if isinstance(parsed, dict) else None
    entry = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "component": "warden_mcp_proxy",
        "server": state.server_name,
        "direction": direction,
        "mode": state.mode.value,
        "method": method,
        "id": msg_id,
        "byte_length": len(raw),
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
    }
    with state.audit_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


async def run_proxy(
    server_name: str,
    command: list[str],
    config_path: Path = DEFAULT_CONFIG_PATH,
    audit_path: Path = DEFAULT_AUDIT_PATH,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> int:
    if not command:
        raise ValueError("wrapped MCP server command is required")

    state = load_proxy_state(server_name, config_path, audit_path)
    state.phase = ProxyPhase.STARTING
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    state.phase = ProxyPhase.RUNNING

    tasks = [
        asyncio.create_task(_pump_client_to_server(proc, state, chunk_size)),
        asyncio.create_task(_pump_server_to_client(proc, state, chunk_size)),
        asyncio.create_task(_pump_stderr(proc, chunk_size)),
    ]
    try:
        await asyncio.gather(*tasks)
        rc = await proc.wait()
        state.phase = ProxyPhase.CLOSED if rc == 0 else ProxyPhase.FAILED
        return rc
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


async def _pump_client_to_server(
    proc: asyncio.subprocess.Process,
    state: ProxyState,
    chunk_size: int,
) -> None:
    assert proc.stdin is not None
    splitter = JsonLineSplitter()
    while True:
        chunk = await asyncio.to_thread(sys.stdin.buffer.read, chunk_size)
        if not chunk:
            break
        for frame in splitter.feed(chunk):
            proc.stdin.write(transform_client_payload(frame, state))
            await proc.stdin.drain()
    tail = splitter.flush()
    if tail:
        proc.stdin.write(transform_client_payload(tail, state))
        await proc.stdin.drain()
    state.phase = ProxyPhase.CLOSING
    proc.stdin.close()
    await proc.stdin.wait_closed()


async def _pump_server_to_client(
    proc: asyncio.subprocess.Process,
    state: ProxyState,
    chunk_size: int,
) -> None:
    assert proc.stdout is not None
    splitter = JsonLineSplitter()
    while True:
        chunk = await proc.stdout.read(chunk_size)
        if not chunk:
            break
        for frame in splitter.feed(chunk):
            await _write_stdout(transform_server_payload(frame, state))
    tail = splitter.flush()
    if tail:
        await _write_stdout(transform_server_payload(tail, state))


async def _pump_stderr(proc: asyncio.subprocess.Process, chunk_size: int) -> None:
    assert proc.stderr is not None
    while True:
        chunk = await proc.stderr.read(chunk_size)
        if not chunk:
            break
        await asyncio.to_thread(sys.stderr.buffer.write, chunk)
        await asyncio.to_thread(sys.stderr.buffer.flush)


async def _write_stdout(payload: bytes) -> None:
    await asyncio.to_thread(sys.stdout.buffer.write, payload)
    await asyncio.to_thread(sys.stdout.buffer.flush)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wrap an MCP stdio server with WARDEN transport calibration.")
    parser.add_argument("--server", required=True, help="MCP server name for cleanroom.json mcp_proxy lookup.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT_PATH)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    add_io_toggle_args(parser)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    ns = parser.parse_args(argv)
    if ns.command and ns.command[0] == "--":
        ns.command = ns.command[1:]
    if not ns.command:
        parser.error("wrapped MCP server command required after --")
    return ns


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(list(argv) if argv is not None else sys.argv[1:])
    if ns.io_channel is not None:
        set_env_mode(ns.io_channel)
    return asyncio.run(
        run_proxy(
            server_name=ns.server,
            command=ns.command,
            config_path=ns.config,
            audit_path=ns.audit,
            chunk_size=max(1, ns.chunk_size),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
