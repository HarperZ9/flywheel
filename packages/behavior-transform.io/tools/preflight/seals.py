"""Cryptographic integrity seals."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .paths import project_root, seal_root
from .receipts import assert_no_secret_markers


SCHEMA = "warden.prefire.seal.v1"
ROOT_FILES = ("AGENTS.md", "README.md", "pyproject.toml", "sitecustomize.py", "warden-prefire.cmd", "warden-prefire.ps1", "warden-prefire.sh")
ROOT_DIRS = ("adapters", "app", "config", "dist/WardenResident", "host-contracts", "profiles", "src/warden_prefire", "warden_prefire")
EXCLUDED_PARTS = {".warden-prefire", ".warden-safe-cache", "__pycache__", ".pytest_cache", "bin", "bundles", "installers", "obj", "tests"}
EXCLUDED_NAMES = {".env"}
EXCLUDED_SUFFIXES = {".pdb", ".pyc", ".pyo"}
REQUIRED_ARTIFACTS = (
    "config/sovereignty-capsule.json",
    "config/surface-manifest.json",
    "config/meta-contract.json",
    "host-contracts/generic.json",
    "app/WardenResident/WardenResident.csproj",
    "app/WardenResident.Core/WardenCommand.cs",
    "dist/WardenResident/WardenResident.exe",
    "src/warden_prefire/cli.py",
    "src/warden_prefire/meta.py",
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _candidate_files(root: Path) -> list[Path]:
    files: dict[str, Path] = {}
    for relative in ROOT_FILES:
        path = root / relative
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path
    for relative in ROOT_DIRS:
        base = root / relative
        if not base.exists():
            continue
        for path in base.rglob("*"):
            rel = path.relative_to(root)
            if path.is_file() and not _excluded(rel):
                files[rel.as_posix()] = path
    return [files[key] for key in sorted(files)]


def _excluded(relative: Path) -> bool:
    parts = set(relative.parts)
    return bool(parts & EXCLUDED_PARTS) or relative.name in EXCLUDED_NAMES or relative.suffix in EXCLUDED_SUFFIXES


def _hash_artifacts(root: Path) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for path in _candidate_files(root):
        rel = path.relative_to(root).as_posix()
        payload = path.read_bytes()
        artifacts[rel] = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    return artifacts


def _resolve_bundle(root: Path, bundle: str | Path | None) -> Path | None:
    if bundle is None:
        return None
    path = Path(bundle)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def build_seal(root: str | Path | None = None, bundle: str | Path | None = None) -> dict[str, Any]:
    base = Path(root).resolve() if root is not None else project_root()
    artifacts = _hash_artifacts(base)
    findings = [{"kind": "missing_required_artifact", "path": rel} for rel in REQUIRED_ARTIFACTS if rel not in artifacts]
    bundle_root = _resolve_bundle(base, bundle)
    bundle_artifacts = _hash_artifacts(bundle_root) if bundle_root and bundle_root.exists() else None
    if bundle_root and not bundle_root.exists():
        findings.append({"kind": "missing_bundle", "path": str(bundle_root)})
    seal = {
        "schema": SCHEMA,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not findings else "fail",
        "root": str(base),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "bundle_root": str(bundle_root) if bundle_root else None,
        "bundle_artifact_count": len(bundle_artifacts or {}),
        "bundle_artifacts": bundle_artifacts or {},
        "findings": findings,
    }
    assert_no_secret_markers(seal)
    return seal


def _verify_artifacts(base: Path, artifacts: dict[str, Any], prefix: str = "") -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for rel, expected in artifacts.items():
        path = base / rel
        if not path.exists():
            findings.append({"kind": f"missing_{prefix}artifact", "path": rel})
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected.get("sha256"):
            findings.append({"kind": f"{prefix}sha256_mismatch", "path": rel})
    return findings


def verify_seal(seal: dict[str, Any], root: str | Path | None = None) -> dict[str, Any]:
    base = Path(root).resolve() if root is not None else Path(seal.get("root", project_root())).resolve()
    findings = _verify_artifacts(base, seal.get("artifacts", {}))
    bundle_artifacts = seal.get("bundle_artifacts", {})
    bundle_root = seal.get("bundle_root")
    if bundle_artifacts and bundle_root:
        findings.extend(_verify_artifacts(Path(bundle_root).resolve(), bundle_artifacts, "bundle_"))
    return {"status": "pass" if not findings else "fail", "findings": findings}


def write_seal(payload: dict[str, Any], target_root: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    target = Path(target_root).resolve() if target_root is not None else seal_root()
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{_timestamp()}.json"
    record = {**payload, "seal_path": str(path)}
    assert_no_secret_markers(record)
    serialized = json.dumps(record, indent=2, sort_keys=True) + "\n"
    path.write_text(serialized, encoding="utf-8")
    (target / "latest.json").write_text(serialized, encoding="utf-8")
    return path, record


def verify_latest_seal() -> dict[str, Any]:
    path = seal_root() / "latest.json"
    if not path.exists():
        return {"status": "fail", "seal_path": str(path), "verified_artifact_count": 0, "findings": [{"kind": "missing_latest_seal", "path": str(path)}]}
    seal = json.loads(path.read_text(encoding="utf-8"))
    result = verify_seal(seal)
    result.update(
        {
            "seal_path": str(path),
            "verified_artifact_count": len(seal.get("artifacts", {})) + len(seal.get("bundle_artifacts", {})),
        }
    )
    return result
