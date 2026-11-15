#!/usr/bin/env python3
"""Flagship status, doctor, and demo envelopes for behavior-transform.io."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "project-telos.flagship-action/v1"

REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "CLAUDE.md",
    "USAGE.md",
    "AUTHORS.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "CHANGELOG.md",
    "pyproject.toml",
    "docs/INTEGRATION_CONTRACT.md",
    "assets/behavior-transform-hero.svg",
    ".github/workflows/ci.yml",
    "tools/io_state.py",
    "tools/safe_read.py",
    "tools/safe_write.py",
    "tools/safe_exec.py",
    "tools/safe_fetch.py",
    "tools/safe_input.py",
    "tools/safe_classify.py",
    "hooks/safe-read-redirect.py",
    "profiles/warden-profile.ps1",
)


def _read_text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _version() -> str:
    data = tomllib.loads(_read_text("pyproject.toml"))
    return data.get("project", {}).get("version", "0.0.0")


def _sha256_prefix(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]


def _native() -> dict[str, Any]:
    return {
        "role": "io-boundary-calibration-layer",
        "project": "Project Telos private line",
        "operator_commands": ["status", "doctor", "demo"],
        "host_surfaces": [
            "CLI JSON",
            "Claude Code hooks",
            "Codex-safe wrapper scripts",
            "shell profiles",
            "future MCP adapter",
        ],
        "schemas": [
            SCHEMA,
            "project-telos.action-receipt/v1",
            "project-telos.context-envelope/v1",
        ],
        "privacy_boundary": (
            "The host receives mode, profile, tool names, counts, hashes, and "
            "verdicts. Raw prompt bodies, private file contents, and secret "
            "values stay inside local IO adapters."
        ),
        "runtime_contract": {
            "default_profile": "ops",
            "passthrough_profiles": ["research", "academic"],
            "receipt_required_for": ["write", "exec", "fetch", "model-boundary"],
            "raw_secret_export": False,
        },
    }


def _envelope(command: str, status: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "tool": "behavior-transform.io",
        "tool_version": _version(),
        "command": command,
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": [],
        "outputs": [],
        "receipts": [],
        "native": _native(),
        "diagnostics": [],
    }


def status_envelope() -> dict[str, Any]:
    envelope = _envelope("status", "MATCH")
    envelope["outputs"] = [{
        "kind": "workspace",
        "root_sha256_prefix": _sha256_prefix("pyproject.toml"),
        "required_files": list(REQUIRED_FILES),
    }]
    return envelope


def _doctor_checks() -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for rel in REQUIRED_FILES:
        checks.append({
            "id": f"required:{rel}",
            "status": "MATCH" if (ROOT / rel).exists() else "DRIFT",
            "evidence_ref": rel,
        })

    claude = _read_text("CLAUDE.md") if (ROOT / "CLAUDE.md").exists() else ""
    contract = (
        _read_text("docs/INTEGRATION_CONTRACT.md")
        if (ROOT / "docs/INTEGRATION_CONTRACT.md").exists()
        else ""
    )
    checks.extend([
        {
            "id": "no-offensive-layer",
            "status": "MATCH" if "Add offensive tooling" in claude else "DRIFT",
            "evidence_ref": "CLAUDE.md#never",
        },
        {
            "id": "raw-secret-boundary",
            "status": "MATCH" if "secret values" in contract else "DRIFT",
            "evidence_ref": "docs/INTEGRATION_CONTRACT.md#privacy-boundary",
        },
        {
            "id": "console-script:behavior-transform",
            "status": "MATCH" if _console_script_points_to_main("behavior-transform") else "DRIFT",
            "evidence_ref": "pyproject.toml#project.scripts",
        },
        {
            "id": "console-script:behavior-transform-io",
            "status": "MATCH" if _console_script_points_to_main("behavior-transform-io") else "DRIFT",
            "evidence_ref": "pyproject.toml#project.scripts",
        },
    ])
    return checks


def _console_script_points_to_main(name: str) -> bool:
    try:
        data = tomllib.loads(_read_text("pyproject.toml"))
    except tomllib.TOMLDecodeError:
        return False
    scripts = data.get("project", {}).get("scripts", {})
    return scripts.get(name) == "tools.behavior_flagship:main"


def doctor_envelope() -> dict[str, Any]:
    checks = _doctor_checks()
    status = "MATCH" if all(check["status"] == "MATCH" for check in checks) else "DRIFT"
    envelope = _envelope("doctor", status)
    envelope["outputs"] = [{"kind": "checks", "items": checks}]
    envelope["diagnostics"] = [check for check in checks if check["status"] != "MATCH"]
    return envelope


def demo_envelope() -> dict[str, Any]:
    envelope = _envelope("demo", "MATCH")
    envelope["outputs"] = [{
        "kind": "demo-plan",
        "name": "IO boundary mode switch",
        "runtime_surface": "local_io",
        "steps": [
            "read current IO mode",
            "switch to research passthrough",
            "switch back to ops calibration",
            "run safe wrapper tests",
            "emit envelope with mode/profile evidence",
        ],
    }]
    return envelope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="behavior-transform.io flagship envelope")
    parser.add_argument("command", choices=("status", "doctor", "demo"))
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    if args.command == "status":
        envelope = status_envelope()
    elif args.command == "doctor":
        envelope = doctor_envelope()
    else:
        envelope = demo_envelope()

    if args.json:
        print(json.dumps(envelope, indent=2, sort_keys=True))
    else:
        print(f"behavior-transform.io {args.command}: {envelope['status']}")
    return 0 if envelope["status"] == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
