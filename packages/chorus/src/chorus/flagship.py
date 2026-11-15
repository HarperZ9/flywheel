"""flagship.py -- chorus's operator-spine envelopes (status, doctor).

Honest by construction, mirroring the crucible lesson: the informational envelope
defaults to the operational token "OK", never a verdict token (MATCH/DRIFT/
UNVERIFIABLE) -- status and doctor measure nothing, so they must not render a
verdict. doctor resolves each capability's live entry point and reports
"available"/"absent", a diagnostic that can actually fail, never a hardcoded pass.
"""
from __future__ import annotations

import importlib

from chorus import __version__

SCHEMA = "project-telos.flagship-action/v1"
TOOL = "chorus"
PRIMARY_COMMANDS = ["run", "decision", "corpora", "daemon", "watch", "digests", "mcp"]


def envelope(command: str, *, status: str = "OK", native: dict | None = None,
             next_actions: list[dict] | None = None) -> dict:
    # status defaults to the operational token "OK": status/doctor measure nothing, so they never
    # render a verdict token. A verdict is emitted only where a receipt was actually derived (a run).
    return {
        "schema": SCHEMA,
        "tool": TOOL,
        "tool_version": __version__,
        "command": command,
        "status": status,
        "inputs": [],
        "outputs": [],
        "receipts": [],
        "native": native or {},
        "next_actions": next_actions or [],
    }


def _next(tool: str, action: str, reason: str) -> dict:
    return {"tool": tool, "action": action, "reason": reason, "inputs": [], "priority": "normal"}


def status_payload() -> dict:
    return envelope(
        "status",
        native={
            "role": "discourse-synthesis",
            "identity": "weighted, clustered, re-checkable readings of a comment corpus; "
                        "sentiment is a weight, never a verdict; every digest carries a receipt",
            "commands": PRIMARY_COMMANDS,
            "operator_commands": ["status", "doctor", "mcp"],
            "mcp_tools": ["chorus.status", "chorus.doctor", "chorus.run",
                          "chorus.decision", "chorus.corpora", "chorus.digests"],
            "orbits": "gather (perceives the corpus; chorus synthesizes the discourse)",
        },
        next_actions=[_next("gather", "docs", "capture a comment corpus before synthesis")],
    )


def _capability(module: str, attr: str) -> str:
    """'available' when the callable is importable and present, else 'absent'. Never a verdict."""
    try:
        return "available" if callable(getattr(importlib.import_module(module), attr, None)) else "absent"
    except Exception:
        return "absent"


def doctor_payload() -> dict:
    checks = [
        {"name": "synthesis", "status": _capability("chorus.synthesize", "synthesize")},
        {"name": "receipt_verify", "status": _capability("chorus.receipt", "verify")},
        {"name": "source_decision", "status": _capability("chorus.decision", "build_decision")},
        {"name": "corpus_discovery", "status": _capability("chorus.corpora", "list_corpora")},
        {"name": "daemon", "status": _capability("chorus.daemon", "tick")},
        {"name": "model_overlay", "status": _capability("chorus.sentiment", "model_pass")},
    ]
    return envelope("doctor", native={"checks": checks})
