"""Shared model and helpers for installed-launch acceptance."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import socket
import subprocess
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    from .installed_launch_acceptance_contract import (
        ASSERTION_IDS, PHASE_ASSERTIONS, PHASE_IDS, completion_from_rows,
        phase_results, validate_receipt_semantics,
    )
except ImportError:
    from installed_launch_acceptance_contract import (  # type: ignore
        ASSERTION_IDS, PHASE_ASSERTIONS, PHASE_IDS, completion_from_rows,
        phase_results, validate_receipt_semantics,
    )

SCHEMA = "flywheel.installed-launch-acceptance/v1"
STATUS_SCHEMA = "flywheel.desktop-status/v1"
APP_ID = "{ecf4cc9b-8a7a-4de2-8e70-0f1ea0f17e5c}"
APP_EXE = "flywheel_desktop.exe"
ENGINE_EXE = "flywheel-gateway.exe"
TOKEN_NAME = "gateway.token"
DOES_NOT_PROVE = [
    "full installer execution unless a release runner attaches that receipt",
    "native UI rendering or CUA-observed user journey",
    "provider OAuth success",
    "model endpoint readiness or quality",
    "Relay worker readiness until separately checked",
    "upgrade behavior without before/after installed snapshots",
    "external source attestation; build manifest is an operator-supplied integrity binding",
]
WINDOW_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class HarnessConfig:
    install_root: Path
    out: Path
    run_id: str = ""
    mode: str = "preflight"
    start_engine: bool = False
    include_local_paths: bool = False
    artifact_root: Path | None = None
    source_commit_expected: str = ""
    expected_version: str = ""
    expected_api_version: int = 1
    expected_app_sha256: str = ""
    expected_engine_sha256: str = ""
    build_manifest: Path | None = None
    expect_installer_payload: bool = False
    require_desktop_shortcut: bool = False
    before_receipt: Path | None = None
    after_receipt: Path | None = None
    port: int = 0


@dataclass
class ShortcutRecord:
    name: str
    target: Path


@dataclass
class MetadataResult:
    state: str
    observed: Any = None
    reason: str = ""


@dataclass
class ProcessHandle:
    pid: int
    proc: Any = None
    job_object_assigned: bool = False
    job_error: str = ""


class ReceiptError(RuntimeError):
    pass


class FixedClock:
    def __init__(self, value: str):
        self.value = value

    def now(self) -> str:
        return self.value


class Clock:
    def now(self) -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


class LocalFilesystem:
    def is_file(self, path: Path) -> bool:
        return Path(path).is_file()


class NullWindowsMetadata:
    def start_menu_shortcuts(self) -> list[ShortcutRecord]:
        return []

    def desktop_shortcut(self) -> ShortcutRecord | None:
        return None

    def uninstall_registry(self, app_id: str, install_root: Path | None = None) -> MetadataResult:
        return MetadataResult("UNTESTED", reason="no_windows_adapter")

    def protocol_registration(self, scheme: str) -> MetadataResult:
        return MetadataResult("UNSUPPORTED", reason="not_required")


class NullHttpClient:
    def get_json(self, url: str, token: str | None = None, timeout: float = 2.0):
        return 0, {"error": "not_started"}

    def post_json(self, url: str, payload: Any, token: str | None = None, timeout: float = 2.0):
        return 0, {"error": "not_started"}


class NullProcessController:
    def is_port_open(self, port: int) -> bool:
        return False

    def start_engine(self, exe, args, env, cwd, stdout, stderr) -> ProcessHandle:
        raise RuntimeError("process start not enabled")

    def listener_pids(self, port: int) -> list[int]:
        return []

    def cleanup(self, handle: ProcessHandle, port: int) -> list[int]:
        return []


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assertion_state(receipt: Mapping[str, Any], aid: str) -> str:
    for row in receipt.get("assertions", []):
        if isinstance(row, MappingABC) and row.get("id") == aid:
            return row.get("state", "")
    raise KeyError(aid)


def verify_receipt_file(path: Path, run_id: str) -> dict:
    if not Path(path).is_file():
        raise ReceiptError(f"receipt missing: {path}")
    try:
        receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReceiptError(f"receipt malformed: {exc}") from exc
    if not isinstance(receipt, MappingABC):
        raise ReceiptError("receipt is not an object")
    if receipt.get("schema") != SCHEMA:
        raise ReceiptError("receipt schema mismatch")
    if receipt.get("run_id") != run_id:
        raise ReceiptError("receipt run_id is stale or mismatched")
    if receipt.get("complete") is not True:
        raise ReceiptError("receipt is not complete")
    if not receipt.get("assertions") or not receipt.get("phase_results"):
        raise ReceiptError("receipt is incomplete")
    try:
        semantic_errors = validate_receipt_semantics(receipt)
    except Exception as exc:
        raise ReceiptError(
            "receipt semantic validation failed: validator_exception:"
            + type(exc).__name__
        ) from exc
    if semantic_errors:
        raise ReceiptError("receipt semantic validation failed: " + "; ".join(semantic_errors))
    return receipt


def build_child_environment(base: Mapping[str, str], isolated_root: Path) -> dict[str, str]:
    allow = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "OS",
             "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
             "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "NUMBER_OF_PROCESSORS"}
    env = {k: v for k, v in base.items() if k.upper() in allow}
    root = full_path(isolated_root)
    env.update({"FLYWHEEL_HOME": str(root / "home"), "USERPROFILE": str(root / "user"),
                "TEMP": str(root / "tmp"), "TMP": str(root / "tmp")})
    for name in ("FLYWHEEL_HOME", "USERPROFILE", "TEMP", "TMP"):
        Path(env[name]).mkdir(parents=True, exist_ok=True)
    return env


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def status_state(code: int, body: Any, expected_api_version: int) -> tuple[str, bool]:
    if code != 200:
        return "STATUS_CONTRACT_MISSING", False
    if not isinstance(body, dict) or body.get("schema") != STATUS_SCHEMA:
        return "STATUS_SCHEMA_INVALID", False
    if body.get("api_version") != expected_api_version:
        return "STATUS_VERSION_MISMATCH", False
    required = ("status", "lanes_live", "lanes_total", "compatible")
    if any(k not in body for k in required):
        return "STATUS_SCHEMA_INVALID", False
    if body["status"] not in ("ok", "degraded", "incompatible"):
        return "STATUS_SCHEMA_INVALID", False
    return "PASS", body["status"] in ("ok", "degraded") and body["compatible"] is True


def display_path(path: Path, root: Path, include: bool) -> str:
    full, base = full_path(path), full_path(root)
    if include:
        return str(full)
    try:
        return "<install_root>/" + full.relative_to(base).as_posix()
    except ValueError:
        return "<redacted-local-path>"


def full_path(path: Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def inside(path: Path, root: Path) -> bool:
    try:
        full_path(path).relative_to(full_path(root))
        return True
    except ValueError:
        return False


def same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(str(full_path(a))) == os.path.normcase(str(full_path(b)))


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def redact_token_body(body: Any) -> Any:
    if isinstance(body, dict):
        return {k: redact_token_body(v) for k, v in body.items() if "token" not in k.lower()}
    if isinstance(body, list):
        return [redact_token_body(v) for v in body]
    return body


def registry_values(winreg, key) -> dict:
    out = {}
    for i in range(winreg.QueryInfoKey(key)[1]):
        name, value, _ = winreg.EnumValue(key, i)
        if isinstance(value, str):
            out[name] = value
    return out


def default_commit(repo: Path) -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         creationflags=WINDOW_FLAGS)
    return out.stdout.strip() if out.returncode == 0 else ""


def default_version(pubspec: Path) -> str:
    for line in pubspec.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().split("+", 1)[0]
    return ""
