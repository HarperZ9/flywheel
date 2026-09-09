"""Runtime admission for product E2E journeys."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

from harness.cross_harness_process import _child_env
from harness.e2e_journey_manifest import FUTURE_RUNTIME_KINDS, IMPLEMENTED_RUNTIME_KINDS, JourneyManifest


def _venv_python(executable: Path) -> Path | None:
    candidates = [
        executable.parent / ("python.exe" if os.name == "nt" else "python"),
        executable.parent.parent / "bin" / "python",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _sha_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _query_distribution_metadata(executable: Path, distribution: str,
                                 expected_wheel_sha256: str = "") -> tuple[int, dict[str, Any] | None, str]:
    python = _venv_python(executable)
    if python is None:
        return 1, None, "venv_python_not_found"
    script = f'''
import hashlib, importlib.metadata as md, json, zipfile
from pathlib import Path
from urllib.parse import unquote, urlparse

def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

dist = md.distribution({distribution!r})
direct = None
for item in dist.files or []:
    if str(item).endswith("direct_url.json"):
        path = Path(dist.locate_file(item))
        direct = json.loads(path.read_text(encoding="utf-8"))
        break
editable = bool((direct or {{}}).get("dir_info", {{}}).get("editable", False))
payload = {{
    "name": dist.metadata["Name"],
    "version": dist.version,
    "direct_url": direct,
    "editable": editable,
    "entry_points": [
        {{"group": ep.group, "name": ep.name, "value": ep.value}}
        for ep in dist.entry_points if ep.group == "console_scripts"
    ],
    "package_location": str(Path(dist.locate_file("gather")).resolve()),
}}
expected = {expected_wheel_sha256!r}
if expected:
    url = (direct or {{}}).get("url", "")
    parsed = urlparse(url)
    if parsed.scheme == "file":
        raw_path = unquote(parsed.path)
        if raw_path.startswith("/") and len(raw_path) > 3 and raw_path[2] == ":":
            raw_path = raw_path[1:]
        wheel_path = Path(raw_path)
        payload["wheel_archive_sha256"] = sha_file(wheel_path)
        rows = []
        mismatches = []
        with zipfile.ZipFile(wheel_path) as wheel:
            members = [info for info in wheel.infolist()
                       if not info.is_dir() and not info.filename.endswith(".dist-info/RECORD")]
            for info in sorted(members, key=lambda row: row.filename):
                member = info.filename
                wheel_sha = hashlib.sha256(wheel.read(member)).hexdigest()
                installed = Path(dist.locate_file(member))
                if not installed.exists():
                    mismatches.append({{"path": member, "reason": "missing"}})
                    continue
                installed_sha = sha_file(installed)
                rows.append({{"path": member, "sha256": installed_sha}})
                if installed_sha != wheel_sha:
                    mismatches.append({{"path": member, "reason": "sha256_mismatch",
                                       "expected": wheel_sha, "observed": installed_sha}})
        payload["wheel_file_count"] = len(members)
        payload["installed_file_count"] = len(rows)
        payload["installed_file_mismatches"] = mismatches
        payload["installed_files_sha256"] = hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
print(json.dumps(payload, sort_keys=True))
'''
    env = _child_env()
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [str(python), "-c", script], cwd=str(executable.parent), env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    if proc.returncode != 0:
        return proc.returncode, None, proc.stderr[-2000:]
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return 1, None, f"distribution_metadata_malformed: {exc}"
    return (0, payload, "") if isinstance(payload, dict) else (1, None, "distribution_metadata_not_object")


def _blocked(kind: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": "blocked", "reason": reason, "kind": kind, **extra}


def preflight_runtime(manifest: JourneyManifest) -> dict[str, Any]:
    runtime = manifest.runtime
    if runtime.kind in FUTURE_RUNTIME_KINDS or runtime.kind not in IMPLEMENTED_RUNTIME_KINDS:
        return _blocked(runtime.kind, "runtime_unsupported", source="unavailable")
    if runtime.forbid_pythonpath and os.environ.get("PYTHONPATH"):
        return _blocked(runtime.kind, "pythonpath_forbidden", source="environment")
    raw_executable = os.environ.get(runtime.executable_env, "")
    if not raw_executable:
        return _blocked(runtime.kind, "runtime_unavailable", source="environment")
    executable = Path(raw_executable)
    if not executable.exists() or not executable.is_file():
        return _blocked(runtime.kind, "runtime_unavailable", executable=raw_executable, source="environment")
    executable = executable.resolve(strict=True)
    executable_sha256 = _sha_file(executable)
    if runtime.expected_executable_sha256 and executable_sha256 != runtime.expected_executable_sha256:
        return _blocked(runtime.kind, "runtime_executable_hash_mismatch", executable=str(executable),
                        executable_sha256=executable_sha256, source="installed_process")

    env = _child_env()
    env.pop("PYTHONPATH", None)
    version = subprocess.run(
        [str(executable), "--version"], cwd=str(executable.parent), env=env,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    version_text = (version.stdout or version.stderr).strip()
    observed_version = version_text.split()[-1] if version_text else ""
    if version.returncode != 0 or not observed_version.startswith(runtime.expected_version_prefix):
        return _blocked(runtime.kind, "runtime_version_mismatch", executable=str(executable),
                        observed_version=version_text, source="installed_process")

    code, metadata, error = _query_distribution_metadata(
        executable, runtime.expected_distribution, runtime.expected_wheel_sha256)
    if code != 0 or metadata is None:
        return _blocked(runtime.kind, "distribution_metadata_unavailable", executable=str(executable),
                        error=error, source="installed_distribution")
    if metadata.get("version") != observed_version:
        return _blocked(runtime.kind, "distribution_version_mismatch", executable=str(executable),
                        observed_version=version_text, metadata=metadata, source="installed_distribution")
    if not str(metadata.get("version", "")).startswith(runtime.expected_version_prefix):
        return _blocked(runtime.kind, "runtime_version_mismatch", executable=str(executable),
                        metadata=metadata, source="installed_distribution")
    if runtime.forbid_editable and metadata.get("editable"):
        return _blocked(runtime.kind, "runtime_editable", executable=str(executable),
                        metadata=metadata, source="installed_distribution")

    direct = metadata.get("direct_url") or {}
    hashes = ((direct.get("archive_info") or {}).get("hashes") or {}) if isinstance(direct, dict) else {}
    if runtime.expected_wheel_sha256 and hashes.get("sha256") != runtime.expected_wheel_sha256:
        return _blocked(runtime.kind, "runtime_wheel_hash_mismatch", executable=str(executable),
                        metadata=metadata, source="installed_distribution")
    if runtime.expected_wheel_sha256 and not metadata.get("installed_files_sha256"):
        return _blocked(runtime.kind, "installed_file_manifest_missing", executable=str(executable),
                        metadata=metadata, source="installed_distribution")
    if runtime.expected_wheel_sha256 and metadata.get("wheel_archive_sha256") != runtime.expected_wheel_sha256:
        return _blocked(runtime.kind, "runtime_wheel_hash_mismatch", executable=str(executable),
                        metadata=metadata, source="installed_distribution")
    if metadata.get("installed_file_mismatches"):
        return _blocked(runtime.kind, "installed_file_mismatch", executable=str(executable),
                        metadata=metadata, source="installed_distribution")
    entry_points = metadata.get("entry_points", [])
    if not any(item.get("name") == "gather" and item.get("value") == "gather.cli:main"
               for item in entry_points if isinstance(item, dict)):
        return _blocked(runtime.kind, "runtime_entrypoint_mismatch", executable=str(executable),
                        metadata=metadata, source="installed_distribution")

    return {
        "status": "ready", "kind": runtime.kind, "executable": str(executable),
        "executable_sha256": executable_sha256,
        "version": str(metadata.get("version")), "distribution": metadata.get("name"),
        "direct_url": direct, "editable": bool(metadata.get("editable")),
        "installed_files_sha256": metadata.get("installed_files_sha256"),
        "wheel_archive_sha256": metadata.get("wheel_archive_sha256"),
        "wheel_file_count": metadata.get("wheel_file_count"),
        "installed_file_count": metadata.get("installed_file_count"),
        "entry_points": entry_points,
        "package_location": metadata.get("package_location"), "source": "installed_wheel_or_venv",
    }
