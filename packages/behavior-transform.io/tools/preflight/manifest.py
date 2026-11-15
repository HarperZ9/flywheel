"""Surface manifest loader + validator."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA = "warden.prefire.surface-manifest.v1"


@dataclass(frozen=True)
class Manifest:
    path: Path
    root: Path
    data: dict[str, Any]
    sha256: str


@dataclass(frozen=True)
class CheckResult:
    status: str
    message: str
    findings: list[dict[str, str]]


def _hash_manifest(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_manifest(path: Path) -> Manifest:
    resolved = path.expanduser().resolve()
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if data.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported manifest schema: {data.get('schema')}")
    if not isinstance(data.get("surfaces"), dict):
        raise ValueError("manifest must define surfaces object")
    root = resolved.parent.parent if resolved.parent.name == "config" else resolved.parent
    return Manifest(path=resolved, root=root, data=data, sha256=_hash_manifest(data))


def _resolve_manifest_path(manifest: Manifest, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return manifest.root / path


def surface_config(manifest: Manifest, surface: str) -> dict[str, Any]:
    config = dict(manifest.data["surfaces"][surface])
    if "io_channel" in config:
        config["io_channel"] = str(_resolve_manifest_path(manifest, config["io_channel"]))
    if "required_paths" in config:
        config["required_paths"] = [
            str(_resolve_manifest_path(manifest, raw_path))
            for raw_path in config["required_paths"]
        ]
    return config


def check_surface(manifest: Manifest, surface: str) -> CheckResult:
    surfaces = manifest.data["surfaces"]
    if surface not in surfaces:
        valid = ", ".join(sorted(surfaces))
        return CheckResult("fail", f"unknown surface {surface}; valid: {valid}", [])

    findings: list[dict[str, str]] = []
    for raw_path in surfaces[surface].get("required_paths", []):
        required_path = _resolve_manifest_path(manifest, raw_path)
        if not required_path.exists():
            findings.append(
                {
                    "kind": "missing_required_path",
                    "path": str(required_path),
                    "surface": surface,
                }
            )

    if findings:
        missing = ", ".join(item["path"] for item in findings)
        return CheckResult("fail", f"missing required path(s): {missing}", findings)
    return CheckResult("pass", f"surface {surface} passed", [])
