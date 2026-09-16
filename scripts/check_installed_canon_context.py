"""Post-install Canon context smoke for an installed Flywheel engine."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
from typing import Any

SCHEMA = "flywheel.installed-canon-context-smoke/v1"
SUMMARY_SCHEMA = SCHEMA + "-summary"
FROZEN_CONTEXT_SCHEMA = "flywheel.frozen-context-memory-smoke/v1"
FROZEN_PAYLOAD_SCHEMA = "flywheel.frozen-canon-context-payload/v1"
CANON_PIN = "ba13fc3fc7582fbc1ae1a720e5cd86ea124d7675"
ENGINE_RELATIVE = Path("engine") / "flywheel-gateway.exe"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_RE = re.compile(r"[0-9a-f]{40}\Z")

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import check_frozen_gateway

LIMITS = [
    "post-install engine smoke only; native Flutter UI is not launched",
    "source_commit is caller-supplied build attestation, not proven by this wrapper",
    "engine hash, version, bundled Canon pin, and Canon context API behavior are checked",
    "Canon context uses a fresh isolated temporary database from the reused frozen smoke",
    "ordinary path checks do not prove adversarial TOCTOU immunity",
]


class SmokeFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-engine-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": "HOLD",
        "expected_version": args.expected_version,
        "limits": list(LIMITS),
    }
    try:
        _run(args, receipt)
        receipt["verdict"] = "PASS"
    except SmokeFailure as exc:
        receipt["failure"] = {"code": exc.code}
    except Exception as exc:  # defensive: do not echo arbitrary exception text.
        receipt["failure"] = {"code": _exception_code(exc)}
    _write_receipt(args.receipt, receipt)
    summary = {"schema": SUMMARY_SCHEMA, "verdict": receipt["verdict"]}
    if receipt["verdict"] != "PASS":
        summary["failure"] = receipt.get("failure", {}).get("code", "UNKNOWN_FAILURE")
    print(json.dumps(summary, sort_keys=True))
    return 0 if receipt["verdict"] == "PASS" else 1


def _run(args: argparse.Namespace, receipt: dict[str, Any]) -> None:
    source_commit = _validate_source_commit(args.source_commit)
    expected_sha = _validate_sha256(args.expected_engine_sha256, "EXPECTED_ENGINE_SHA256_INVALID")
    engine = _resolve_engine(args.install_root)
    before = _sha256_file(engine)
    receipt["source"] = {"commit": source_commit, "attestation": "caller-supplied"}
    receipt["engine"] = {
        "path": "<install_root>/" + ENGINE_RELATIVE.as_posix(),
        "expected_sha256": expected_sha,
        "sha256_before": before,
    }
    if before != expected_sha:
        raise SmokeFailure("ENGINE_SHA256_MISMATCH_BEFORE")
    frozen_receipt = _frozen_receipt(args.expected_version)
    try:
        check_frozen_gateway.check(engine, args.expected_version, frozen_receipt)
    except Exception as exc:
        raise SmokeFailure(_exception_code(exc)) from exc
    _validate_smoke(frozen_receipt, args.expected_version)
    after = _sha256_file(engine)
    receipt["engine"]["sha256_after"] = after
    if after != before:
        raise SmokeFailure("ENGINE_SHA256_CHANGED_DURING_SMOKE")
    if after != expected_sha:
        raise SmokeFailure("ENGINE_SHA256_MISMATCH_AFTER")
    receipt["engine"].update({"sha256": after, "hash_verified_before_after": True})
    receipt["observed_version"] = frozen_receipt.get("version")
    receipt["canon"] = _bounded_payload(frozen_receipt["canon_context_payload"])
    receipt["context_memory"] = _bounded_context(frozen_receipt["context_memory_acceptance"])
    receipt["cleanup"] = {"owned_process_terminal": True, "isolated_runtime_removed": True}
    receipt["frozen_smoke"] = {
        "schema": frozen_receipt.get("schema"),
        "reused_existing_checker": True,
        "scope": "installed engine executable under install root",
    }


def _frozen_receipt(expected_version: str) -> dict[str, Any]:
    return {
        "schema": "flywheel.frozen-gateway-smoke/v1",
        "verdict": "HOLD",
        "expected_version": expected_version,
    }


def _resolve_engine(install_root: Path) -> Path:
    _reject_reparse_chain(install_root, "INSTALL_ROOT_REPARSE_POINT")
    try:
        root = install_root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise SmokeFailure("INSTALL_ROOT_MISSING") from exc
    if not root.is_dir():
        raise SmokeFailure("INSTALL_ROOT_NOT_DIRECTORY")
    candidate = root / ENGINE_RELATIVE
    _reject_reparse_chain(candidate, "ENGINE_REPARSE_POINT")
    try:
        engine = candidate.resolve(strict=True)
    except OSError as exc:
        raise SmokeFailure("ENGINE_MISSING") from exc
    try:
        engine.relative_to(root)
    except ValueError as exc:
        raise SmokeFailure("ENGINE_PATH_ESCAPE") from exc
    if not engine.is_file():
        raise SmokeFailure("ENGINE_MISSING")
    return engine


def _reject_reparse_chain(path: Path, code: str) -> None:
    raw = path.expanduser()
    current = raw if raw.is_absolute() else Path.cwd() / raw
    chain: list[Path] = []
    while True:
        if current.exists() or current.is_symlink():
            chain.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    for item in chain:
        if _is_reparse_point(item):
            raise SmokeFailure(code)


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if path.is_symlink():
        return True
    attrs = getattr(info, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _validate_smoke(frozen: dict[str, Any], expected_version: str) -> None:
    if frozen.get("version") != expected_version:
        raise SmokeFailure("INSTALLED_GATEWAY_VERSION_MISMATCH")
    payload = frozen.get("canon_context_payload")
    if not isinstance(payload, dict):
        raise SmokeFailure("CANON_PAYLOAD_MISSING")
    _validate_payload(payload)
    context = frozen.get("context_memory_acceptance")
    if not isinstance(context, dict):
        raise SmokeFailure("CONTEXT_RESULT_MISSING")
    _validate_context(context)
    if frozen.get("owned_process_terminal") is not True:
        raise SmokeFailure("OWNED_PROCESS_NOT_TERMINAL")
    if frozen.get("isolated_runtime_removed") is not True:
        raise SmokeFailure("ISOLATED_RUNTIME_NOT_REMOVED")


def _validate_payload(payload: dict[str, Any]) -> None:
    if payload.get("schema") != FROZEN_PAYLOAD_SCHEMA:
        raise SmokeFailure("CANON_PAYLOAD_SCHEMA")
    if payload.get("owner_commit") != CANON_PIN:
        raise SmokeFailure("CANON_CONTEXT_PIN_COMMIT")
    if not _sha256_uri(payload.get("source_manifest_sha256")):
        raise SmokeFailure("CANON_SOURCE_MANIFEST_HASH")
    if payload.get("license_present") is not True:
        raise SmokeFailure("CANON_LICENSE_MISSING")
    if not _sha256_uri(payload.get("license_sha256")):
        raise SmokeFailure("CANON_LICENSE_HASH")
    license_path = str(payload.get("license_path") or "")
    if not license_path or Path(license_path).is_absolute() or ":" in license_path:
        raise SmokeFailure("CANON_LICENSE_PATH_UNBOUNDED")


def _validate_context(context: dict[str, Any]) -> None:
    if context.get("schema") != FROZEN_CONTEXT_SCHEMA:
        raise SmokeFailure("CONTEXT_RESULT_SCHEMA")
    if context.get("capture_status") not in {"stored", "already_present"}:
        raise SmokeFailure("CONTEXT_CAPTURE_RESULT_MISSING")
    if context.get("preflight_status") != "found_in_searched_sources":
        raise SmokeFailure("CONTEXT_PREFLIGHT_RESULT_MISSING")
    if not isinstance(context.get("hit_count"), int) or context["hit_count"] < 1:
        raise SmokeFailure("CONTEXT_PREFLIGHT_RESULT_MISSING")
    if context.get("denied_project_code") != "CONTEXT_SCOPE_NOT_BOUND":
        raise SmokeFailure("CONTEXT_PROJECT_DENIAL_MISSING")
    if context.get("denied_owner_code") != "CONTEXT_OWNER_NOT_BOUND":
        raise SmokeFailure("CONTEXT_OWNER_DENIAL_MISSING")
    if context.get("tampered_evidence_code") != "CANON_CONTEXT_TOOL_ERROR":
        raise SmokeFailure("CONTEXT_TAMPER_RESULT_MISSING")
    if not _event_record_id(context.get("event_record_id")):
        raise SmokeFailure("CONTEXT_EVENT_RECORD_ID_MISSING")
    if not _plain_sha256(context.get("source_hash")):
        raise SmokeFailure("CONTEXT_SOURCE_HASH_MISSING")


def _bounded_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": FROZEN_PAYLOAD_SCHEMA,
        "owner_commit": payload["owner_commit"],
        "source_manifest_sha256": payload["source_manifest_sha256"],
        "license_sha256": payload["license_sha256"],
        "license_present": True,
        "license_path": payload["license_path"],
    }


def _bounded_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": FROZEN_CONTEXT_SCHEMA,
        "capture_status": context["capture_status"],
        "preflight_status": context["preflight_status"],
        "hit_count": context["hit_count"],
        "denied_project_code": context["denied_project_code"],
        "denied_owner_code": context["denied_owner_code"],
        "tampered_evidence_code": context["tampered_evidence_code"],
        "event_record_id": context["event_record_id"],
        "source_hash": context["source_hash"],
        "owner_ref_bound_present": bool(context.get("owner_ref_bound")),
    }


def _validate_source_commit(value: str) -> str:
    if not _SOURCE_RE.fullmatch(value or ""):
        raise SmokeFailure("SOURCE_COMMIT_INVALID")
    return value


def _validate_sha256(value: str, code: str) -> str:
    if not _plain_sha256(value):
        raise SmokeFailure(code)
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plain_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _sha256_uri(value: object) -> bool:
    return isinstance(value, str) and value.startswith("sha256:") and _plain_sha256(value[7:])


def _event_record_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"context-event-[0-9a-f]{64}", value) is not None


def _exception_code(exc: Exception) -> str:
    if isinstance(exc, RuntimeError):
        return "FROZEN_SMOKE_FAILED"
    return type(exc).__name__


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
