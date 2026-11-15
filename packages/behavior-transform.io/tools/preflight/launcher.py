"""High-level launch orchestrator.

Validates seal, capsule, manifest, surface, then spawns the child
process with all preflight state embedded in the environment.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from .activation import state_root, write_activation_state
from .capsule import build_model_packet, load_capsule
from .manifest import check_surface, load_manifest, surface_config
from .meta import augment_model_packet
from .native import resolve_native_command
from .paths import capsule_path, manifest_path, project_root, receipt_root
from .receipts import write_receipt
from .runner import build_launch_env, run_child
from .seals import verify_latest_seal


def _hash_command(command: list[str]) -> str:
    return hashlib.sha256(json.dumps(command, separators=(",", ":")).encode("utf-8")).hexdigest()


def _command_preview(command: list[str]) -> str:
    preview = " ".join(command)
    return preview if len(preview) <= 200 else preview[:197] + "..."


def _normalize_io_mode(value: str | None) -> str:
    if value is not None:
        return value
    raw = os.environ.get("WARDEN_IO_CHANNEL") or os.environ.get("WARDEN_IO")
    if raw and raw.strip().lower() in {"0", "false", "no", "off", "raw", "native"}:
        return "off"
    return "on"


def launch(
    child: list[str],
    surface: str,
    host: str,
    io_mode: str | None = None,
    enforce_auth: bool = True,
) -> dict[str, Any]:
    """Full preflight verification + child process launch.

    Returns a status dict with exit_code, state_path, receipt_path.
    When enforce_auth is True, the authority gate is checked before
    any seal, capsule, or manifest validation.
    """
    if not child:
        raise ValueError("child command is required")

    if enforce_auth:
        try:
            from authority_gate import gate_launch
            gate_result = gate_launch(surface=surface)
            if not gate_result.allowed:
                return {
                    "status": "fail",
                    "surface": surface,
                    "message": f"authority gate denied: {gate_result.reason}",
                    "gate": gate_result.to_dict(),
                    "findings": [],
                }
        except ImportError:
            pass

    try:
        child = resolve_native_command(child)
    except ValueError as exc:
        return {"status": "fail", "surface": surface, "message": str(exc), "findings": []}

    seal = verify_latest_seal()
    if seal["status"] != "pass":
        return {"status": "fail", "surface": surface, "seal": seal, "findings": seal.get("findings", [])}

    root = project_root()
    mode = _normalize_io_mode(io_mode)
    capsule = load_capsule(capsule_path())
    manifest = load_manifest(manifest_path())
    surface_check = check_surface(manifest, surface)
    if surface_check.status != "pass":
        return {"status": "fail", "surface": surface, "findings": surface_check.findings}

    latest = receipt_root() / surface / "latest.json"
    packet = augment_model_packet(build_model_packet(capsule, surface, mode, manifest.sha256, latest), surface)
    receipt_path = write_receipt(
        receipt_root(),
        {
            "surface": surface,
            "status": "pass",
            "manifest_sha256": manifest.sha256,
            "sovereignty_capsule_sha256": capsule.sha256,
            "federal_appointment_state": capsule.data["federal_appointment"]["state"],
            "oversight_principals": capsule.data["oversight_principals"],
            "io_mode": mode,
            "command_sha256": _hash_command(child),
            "command_preview": _command_preview(child),
            "repo_root": str(root),
            "tool_versions": {"python": sys.version.split()[0]},
            "findings": [],
            "model_packet": packet,
        },
    )
    packet["warden_prefire"]["receipt"] = str(receipt_path)
    state_path = write_activation_state(
        state_root(root), surface, mode,
        {"status": "pass", "receipt_path": str(receipt_path), "model_packet": packet},
    )
    env = build_launch_env(os.environ.copy(), root, state_path, receipt_path, surface, host)
    io_channel = Path(surface_config(manifest, surface)["io_channel"])
    exit_code = run_child(sys.executable, io_channel, mode, child, Path.cwd(), extra_env=env)

    return {
        "status": "pass" if exit_code == 0 else "fail",
        "exit_code": exit_code,
        "host": host,
        "surface": surface,
        "state_path": str(state_path),
        "receipt_path": str(receipt_path),
    }
