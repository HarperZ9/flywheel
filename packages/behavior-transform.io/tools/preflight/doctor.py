"""Health check for the preflight subsystem."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .capsule import load_capsule
from .manifest import check_surface, load_manifest
from .paths import capsule_path, manifest_path, project_root


SURFACES = ("codex_app", "codex_cli", "claude_code", "warden_cli", "generic_cli")
LAUNCHERS = ("warden-prefire.cmd", "warden-prefire.ps1", "warden-prefire.sh")
PROFILES = (
    "profiles/warden-profile.cmd",
    "profiles/warden-profile.ps1",
    "profiles/warden-profile.sh",
)
ADAPTERS = (
    "adapters/codex-session-start.ps1",
    "adapters/codex-session-start.cmd",
    "adapters/claude-session-start.sh",
    "adapters/generic-session-start.sh",
)


def _exists(root: Path, relative_paths: tuple[str, ...]) -> tuple[str, list[str]]:
    missing = [path for path in relative_paths if not (root / path).exists()]
    return ("pass" if not missing else "fail"), missing


def run_doctor(bundle: str | Path | None = None) -> dict[str, Any]:
    root = project_root()
    checks: dict[str, str] = {}
    findings: list[dict[str, Any]] = []

    try:
        capsule = load_capsule(capsule_path())
        checks["capsule"] = "pass"
    except Exception as exc:
        capsule = None
        checks["capsule"] = "fail"
        findings.append({"check": "capsule", "message": str(exc)})

    try:
        manifest = load_manifest(manifest_path())
        surface_results = [check_surface(manifest, surface) for surface in SURFACES]
        checks["surfaces"] = "pass" if all(r.status == "pass" for r in surface_results) else "fail"
        for result in surface_results:
            for finding in result.findings:
                findings.append({"check": "surfaces", **finding})
    except Exception as exc:
        manifest = None
        checks["surfaces"] = "fail"
        findings.append({"check": "surfaces", "message": str(exc)})

    for name, paths in (
        ("launchers", LAUNCHERS),
        ("profiles", PROFILES),
        ("adapters", ADAPTERS),
    ):
        status, missing = _exists(root, paths)
        checks[name] = status
        for path in missing:
            findings.append({"check": name, "missing": path})

    status = "pass" if all(value == "pass" for value in checks.values()) else "fail"
    return {
        "status": status,
        "checks": checks,
        "findings": findings,
        "surface_count": len(SURFACES),
        "capsule_sha256": capsule.sha256 if capsule is not None else None,
        "manifest_sha256": manifest.sha256 if manifest is not None else None,
    }


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
