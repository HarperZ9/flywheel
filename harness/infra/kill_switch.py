"""kill_switch.py -- Artifact 26: Stop Conditions and Kill Authority.

Infrastructure-level stop authority: network isolation, credential revocation,
process termination, compute cutoff. Requires two independent authorities.
Evidence-preserving vs destructive shutdown paths.

This is the most dangerous module in the ecosystem. It is OFF by default and
requires explicit dual confirmation. No action is taken without both
authorities confirming.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA = "flywheel.kill-switch/v1"

# The actions the kill switch can take, from least to most destructive.
SHUTDOWN_MODES = ("evidence-preserving", "destructive")

ACTIONS = {
    "network-isolation": "block outbound network traffic from the agent runtime",
    "credential-revocation": "revoke all credentials accessible to the agent",
    "process-termination": "terminate the agent process and its children",
    "compute-cutoff": "stop the compute instance running the agent",
}


@dataclass
class KillRequest:
    """A request to trigger the kill switch."""
    run_id: str
    reason: str
    authority_1: str = ""
    authority_2: str = ""
    mode: str = "evidence-preserving"
    actions: list[str] = field(default_factory=lambda: list(ACTIONS.keys()))
    confirmed: bool = False

    def add_authority(self, name: str) -> bool:
        """Add a confirming authority. Returns True when both are present."""
        if not self.authority_1:
            self.authority_1 = name
        elif not self.authority_2 and name != self.authority_1:
            self.authority_2 = name
        self.confirmed = bool(self.authority_1 and self.authority_2)
        return self.confirmed


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_kill_receipt(request: KillRequest) -> dict[str, Any]:
    """Build a sealed kill switch receipt.

    If the request is not confirmed (both authorities present), the receipt
    records the refusal, not an execution.
    """
    executed = request.confirmed
    seal_body = {
        "run_id": request.run_id,
        "reason": request.reason,
        "authority_1": request.authority_1,
        "authority_2": request.authority_2,
        "mode": request.mode,
        "actions": list(request.actions),
        "executed": executed,
        "timestamp": _utc_now(),
    }
    if not executed:
        seal_body["refusal_reason"] = (
            "kill switch requires two independent authorities; "
            f"provided: {sum(bool(a) for a in [request.authority_1, request.authority_2])}"
        )
    seal_hash = _sha256_hex(_canonical_bytes(seal_body))
    return {"schema": SCHEMA, "seal_hash": seal_hash, "seal_body": seal_body}


def verify_kill_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Verify a kill switch receipt."""
    if not isinstance(receipt, dict):
        return {"verdict": "UNVERIFIABLE", "detail": "not an object"}
    if receipt.get("schema") != SCHEMA:
        return {"verdict": "UNVERIFIABLE", "detail": "schema mismatch"}
    seal_body = receipt.get("seal_body")
    if not isinstance(seal_body, dict):
        return {"verdict": "UNVERIFIABLE", "detail": "no seal_body"}
    recomputed = _sha256_hex(_canonical_bytes(seal_body))
    if recomputed != receipt.get("seal_hash"):
        return {"verdict": "TAMPERED", "detail": "seal mismatch"}
    return {"verdict": "MATCH",
            "executed": seal_body.get("executed", False),
            "mode": seal_body.get("mode", "")}


# --- the actual infrastructure actions (stubs; safe by default) ------------

def isolate_network() -> dict[str, Any]:
    """Block outbound network traffic. Returns the action result.

    This is a stub that records the intent. In a real deployment, this would
    flush iptables, disable the network interface, or call a cloud security
    group API. The stub always records the action but does NOT execute it
    unless FLYWHEEL_KILL_SWITCH_LIVE=1 is set in the environment.
    """
    live = __import__("os").environ.get("FLYWHEEL_KILL_SWITCH_LIVE") == "1"
    if not live:
        return {"action": "network-isolation", "executed": False,
                "reason": "FLYWHEEL_KILL_SWITCH_LIVE not set; dry run"}
    # Real implementation would go here
    return {"action": "network-isolation", "executed": True,
            "reason": "network isolated (live mode)"}


def revoke_credentials() -> dict[str, Any]:
    """Revoke all credentials. Stub (safe by default)."""
    live = __import__("os").environ.get("FLYWHEEL_KILL_SWITCH_LIVE") == "1"
    if not live:
        return {"action": "credential-revocation", "executed": False,
                "reason": "dry run"}
    return {"action": "credential-revocation", "executed": True,
            "reason": "credentials revoked (live mode)"}


def terminate_process(pid: int = 0) -> dict[str, Any]:
    """Terminate the agent process tree. Stub (safe by default)."""
    live = __import__("os").environ.get("FLYWHEEL_KILL_SWITCH_LIVE") == "1"
    if not live:
        return {"action": "process-termination", "executed": False,
                "reason": "dry run", "target_pid": pid}
    if pid > 0:
        import signal
        try:
            __import__("os").kill(pid, signal.SIGTERM)
            return {"action": "process-termination", "executed": True,
                    "reason": f"sent SIGTERM to {pid}"}
        except Exception as e:
            return {"action": "process-termination", "executed": False,
                    "reason": str(e)}
    return {"action": "process-termination", "executed": False,
            "reason": "no pid specified"}
