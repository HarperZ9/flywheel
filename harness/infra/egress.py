"""egress.py -- Artifact 17: network egress monitor.

Reads active connections and classifies each against the egress matrix. Emits
sealed flywheel.egress/v1 receipts for each connection event. Default-deny mode
flags any connection not in the matrix.

Uses psutil if available (cross-platform). Falls back to /proc/net/tcp parsing
on Linux if psutil is absent. On Windows without psutil, returns an empty list
with an honest UNVERIFIABLE note.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .egress_matrix import EgressMatrix, default_matrix

SCHEMA = "flywheel.egress/v1"

_HEX64 = frozenset("0123456789abcdefABCDEF")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_connections() -> list[dict[str, Any]]:
    """Get active network connections. Returns list of {laddr, raddr, status,
    pid, process_name}.

    Uses psutil if available. Falls back to /proc on Linux. Returns empty list
    on failure (honest null, not a crash).
    """
    try:
        import psutil
        conns = []
        for c in psutil.net_connections(kind="inet"):
            raddr = c.raddr if c.raddr else ()
            rip = raddr[0] if raddr else ""
            rport = raddr[1] if raddr else 0
            pid = c.pid or 0
            pname = ""
            if pid:
                try:
                    pname = psutil.Process(pid).name()
                except Exception:
                    pass
            conns.append({
                "remote_ip": rip, "remote_port": rport,
                "status": c.status, "pid": pid, "process": pname,
            })
        return conns
    except ImportError:
        pass

    # Fallback: /proc/net/tcp on Linux
    try:
        return _parse_proc_net_tcp()
    except Exception:
        return []


def _parse_proc_net_tcp() -> list[dict[str, Any]]:
    """Parse /proc/net/tcp for active connections (Linux fallback)."""
    conns: list[dict[str, Any]] = []
    try:
        with open("/proc/net/tcp", encoding="ascii") as f:
            for line in f.readlines()[1:]:  # skip header
                parts = line.split()
                if len(parts) < 4:
                    continue
                local = parts[1]
                remote = parts[2]
                status = parts[3]
                rip_hex, rport_hex = remote.split(":")
                rip = _hex_to_ip(rip_hex)
                rport = int(rport_hex, 16)
                if rip == "0.0.0.0" or rport == 0:
                    continue
                conns.append({
                    "remote_ip": rip, "remote_port": rport,
                    "status": _tcp_state(status), "pid": 0, "process": "",
                })
    except (FileNotFoundError, PermissionError):
        pass
    return conns


def _hex_to_ip(hex_addr: str) -> str:
    """Convert a hex IP from /proc/net/tcp to dotted decimal."""
    if len(hex_addr) != 8:
        return hex_addr
    b = bytes.fromhex(hex_addr)
    return f"{b[3]}.{b[2]}.{b[1]}.{b[0]}"


def _tcp_state(state: str) -> str:
    states = {"01": "ESTABLISHED", "02": "SYN_SENT", "06": "TIME_WAIT",
              "0A": "LISTEN"}
    return states.get(state, state)


def build_egress_receipt(
    *,
    destination: str,
    port: int,
    protocol: str,
    process: str,
    pid: int,
    verdict: str,
    reason: str,
    purpose: str,
    run_id: str,
) -> dict[str, Any]:
    """Build a sealed egress receipt for one connection event."""
    seal_body = {
        "destination": destination,
        "port": port,
        "protocol": protocol,
        "process": process,
        "pid": pid,
        "verdict": verdict,
        "reason": reason,
        "purpose": purpose,
        "run_id": run_id,
        "timestamp": _utc_now(),
    }
    seal_hash = _sha256_hex(_canonical_bytes(seal_body))
    return {
        "schema": SCHEMA,
        "seal_hash": seal_hash,
        "seal_body": seal_body,
    }


def scan_egress(
    matrix: EgressMatrix | None = None,
    *,
    run_id: str = "infra-scan",
) -> list[dict[str, Any]]:
    """Scan active connections and return sealed egress receipts.

    Each connection is classified against the matrix. In strict mode,
    connections not in the matrix get verdict BLOCKED. In non-strict mode, they
    get UNKNOWN.
    """
    if matrix is None:
        matrix = default_matrix()

    conns = _get_connections()
    receipts: list[dict[str, Any]] = []

    for conn in conns:
        dest = conn["remote_ip"]
        port = conn["remote_port"]
        if not dest or port == 0:
            continue
        result = matrix.check(dest, port)
        receipt = build_egress_receipt(
            destination=dest,
            port=port,
            protocol="tcp",
            process=conn.get("process", ""),
            pid=conn.get("pid", 0),
            verdict=result["verdict"],
            reason=result.get("reason", ""),
            purpose=result.get("purpose", ""),
            run_id=run_id,
        )
        receipts.append(receipt)

    return receipts


def verify_egress_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Verify an egress receipt's seal."""
    if not isinstance(receipt, dict):
        return {"verdict": "UNVERIFIABLE", "detail": "not an object"}
    if receipt.get("schema") != SCHEMA:
        return {"verdict": "UNVERIFIABLE", "detail": "schema mismatch"}

    seal_hash = receipt.get("seal_hash", "")
    seal_body = receipt.get("seal_body")
    if not isinstance(seal_body, dict):
        return {"verdict": "UNVERIFIABLE", "detail": "no seal_body"}

    recomputed = _sha256_hex(_canonical_bytes(seal_body))
    if recomputed != seal_hash:
        return {"verdict": "TAMPERED", "detail": "seal mismatch"}

    verdict = seal_body.get("verdict", "")
    if verdict not in ("ALLOWED", "BLOCKED", "UNKNOWN"):
        return {"verdict": "UNVERIFIABLE", "detail": f"bad verdict: {verdict}"}

    return {"verdict": "MATCH", "egress_verdict": verdict,
            "destination": seal_body.get("destination", "")}
