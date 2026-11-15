"""Activation state writer + env-snippet generator."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


def state_root(default_root: Path) -> Path:
    configured = os.environ.get("WARDEN_PREFIRE_STATE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return default_root / ".warden-prefire" / "state"


def write_activation_state(
    root: Path,
    surface: str,
    io_mode: str,
    packet_payload: dict[str, Any],
) -> Path:
    state_base = root if root.name == "state" else root / "state"
    state_dir = state_base / surface
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "current.json"
    payload = {
        "schema": "warden.prefire.activation-state.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "surface": surface,
        "io_mode": io_mode,
        "status": packet_payload["status"],
        "receipt_path": packet_payload["receipt_path"],
        "model_packet": packet_payload["model_packet"],
    }
    state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state_path


def build_env_snippet(shell: str, state_path: Path, receipt_path: Path, root: Path, surface: str) -> str:
    values = {
        "WARDEN_PREFIRE_ACTIVE": "1",
        "WARDEN_PREFIRE_ROOT": str(root),
        "WARDEN_PREFIRE_STATE": str(state_path),
        "WARDEN_PREFIRE_RECEIPT": str(receipt_path),
        "WARDEN_PREFIRE_SURFACE": surface,
    }
    if shell == "powershell":
        return "".join(f"$env:{key} = '{value}'\n" for key, value in values.items())
    if shell == "cmd":
        return "".join(f"set {key}={value}\r\n" for key, value in values.items())
    if shell == "sh":
        return "".join(f"export {key}='{value}'\n" for key, value in values.items())
    raise ValueError(f"unsupported shell: {shell}")
