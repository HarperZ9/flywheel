"""BuildLang/buildc receipt bridge for the flywheel byte-witness layer.

BuildLang/buildc already emits richer receipts than the local model harness:
source-bound check receipts, scientific-runtime receipts, receipt chains, corpus
receipts, and Crucible/Telos measurement exports. This module imports those
artifacts without pretending that a JSON file alone is a fresh verifier result.

The bridge is deliberately fail-closed:

* a raw receipt becomes a content-addressed byte-witness packet;
* a buildc verification command may be attached;
* only a successful attached verification can promote the packet to MATCH;
* missing verification stays UNVERIFIABLE, not "trusted".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


SCHEMA = "buildlang-flywheel-byte-witness/v1"
MATCH = "MATCH"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_text(body)


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def _dig(data: dict[str, Any], *path: str) -> Any:
    current: Any = data
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _first_present(data: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> Any:
    for path in paths:
        value = _dig(data, *path)
        if value not in (None, "", [], {}):
            return value
    return None


def _extract_buildc_fields(receipt: dict[str, Any]) -> dict[str, Any]:
    invariant = receipt.get("invariant")
    if isinstance(invariant, dict):
        invariant_name = invariant.get("name") or invariant.get("id")
        invariant_status = invariant.get("status") or _dig(invariant, "observed", "status")
    else:
        invariant_name = invariant
        invariant_status = None

    raw_source = receipt.get("source")
    source_path = raw_source if isinstance(raw_source, str) else _first_present(
        receipt,
        (
            ("source", "path"),
            ("source_path",),
            ("provenance", "source_path"),
            ("input", "source_path"),
        ),
    )
    raw_source_digest = receipt.get("source_digest")
    if isinstance(raw_source_digest, dict):
        source_digest = raw_source_digest.get("hex") or raw_source_digest.get("digest")
    elif isinstance(raw_source_digest, str):
        source_digest = raw_source_digest
    else:
        source_digest = _first_present(
            receipt,
            (
                ("source", "sha256"),
                ("source", "digest"),
                ("source_sha256",),
                ("provenance", "source_sha256"),
                ("input", "source_sha256"),
            ),
        )
    raw_input_graph_digest = receipt.get("input_graph_digest")
    if isinstance(raw_input_graph_digest, dict):
        input_graph_digest = raw_input_graph_digest.get("hex") or raw_input_graph_digest.get("digest")
    elif isinstance(raw_input_graph_digest, str):
        input_graph_digest = raw_input_graph_digest
    else:
        input_graph_digest = ""
    seal_hex = _first_present(receipt, (("seal", "hex"), ("seal",), ("receipt_seal",)))
    toolchain = _dig(receipt, "build_state", "toolchain")
    return {
        "schema": receipt.get("schema"),
        "compiler": receipt.get("compiler"),
        "compiler_version": receipt.get("compiler_version"),
        "language_version": receipt.get("language_version"),
        "receipt_status": receipt.get("receipt_status"),
        "source_path": source_path,
        "source_digest": source_digest,
        "input_graph_digest": input_graph_digest,
        "invariant_name": invariant_name,
        "invariant_status": invariant_status,
        "seal_present": bool(seal_hex),
        "seal_hash": _sha256_text(str(seal_hex))[:16] if seal_hex else "",
        "toolchain_present": isinstance(toolchain, dict),
        "toolchain_digest": _canonical_hash(toolchain)[:16] if isinstance(toolchain, dict) else "",
    }


def run_buildc_verify(
    receipt_path: Path,
    *,
    buildc: str = "buildc",
    repo_root: Path | None = None,
    timeout_seconds: int = 120,
    json_report: bool = True,
) -> CommandResult:
    command = [buildc, "receipt", "verify", str(receipt_path)]
    if json_report:
        command.append("--json")
    cwd = str(repo_root or receipt_path.parent)
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(command, cwd, proc.returncode, proc.stdout, proc.stderr)
    except FileNotFoundError as exc:
        return CommandResult(command, cwd, 127, "", str(exc))
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command,
            cwd,
            124,
            exc.stdout or "",
            exc.stderr or f"buildc verify timed out after {timeout_seconds}s",
        )


def _verification_block(command_result: CommandResult | None) -> dict[str, Any]:
    if command_result is None:
        return {
            "attempted": False,
            "command": [],
            "cwd": "",
            "exit_code": None,
            "stdout_sha256": "",
            "stderr_sha256": "",
            "stdout_chars": 0,
            "stderr_chars": 0,
        }
    return {
        "attempted": True,
        "command": command_result.command,
        "cwd": command_result.cwd,
        "exit_code": command_result.exit_code,
        "stdout_sha256": _sha256_text(command_result.stdout),
        "stderr_sha256": _sha256_text(command_result.stderr),
        "stdout_chars": len(command_result.stdout),
        "stderr_chars": len(command_result.stderr),
    }


def _verdict(receipt_fields: dict[str, Any], command_result: CommandResult | None) -> tuple[str, str]:
    if command_result is None:
        return UNVERIFIABLE, "buildc_verification_not_attached"
    if command_result.exit_code == 0:
        return MATCH, ""
    status = str(receipt_fields.get("receipt_status") or "").upper()
    if status in {"FAIL_UNEXPECTED", "UNVERIFIABLE"}:
        return DRIFT, "buildc_receipt_records_failure"
    return UNVERIFIABLE, "buildc_verification_failed"


def bridge_buildc_receipt(
    receipt_path: Path,
    *,
    export_path: Path | None = None,
    repo_root: Path | None = None,
    command_result: CommandResult | None = None,
) -> dict[str, Any]:
    receipt_path = receipt_path.resolve()
    receipt = _load_json(receipt_path)
    receipt_sha = file_sha256(receipt_path)
    export_sha = file_sha256(export_path.resolve()) if export_path else ""
    export_schema = ""
    if export_path:
        export_schema = str(_load_json(export_path.resolve()).get("schema", ""))
    fields = _extract_buildc_fields(receipt)
    verification = _verification_block(command_result)
    verdict, failure_code = _verdict(fields, command_result)
    base = {
        "schema": SCHEMA,
        "source_tool": "buildc",
        "receipt_sha256": receipt_sha,
        "export_sha256": export_sha,
        "verification": verification,
        "verdict": verdict,
        "failure_code": failure_code,
    }
    witness_id = _canonical_hash(base)[:24]
    packet = {
        "schema": SCHEMA,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_tool": "buildc",
        "input": {
            "receipt_path": str(receipt_path),
            "receipt_sha256": receipt_sha,
            "export_path": str(export_path.resolve()) if export_path else "",
            "export_sha256": export_sha,
            "export_schema": export_schema,
            "repo_root": str(repo_root.resolve()) if repo_root else "",
        },
        "buildc": fields,
        "verification": verification,
        "witness": {
            "byte_witness_id": witness_id,
            "receipt_complete": True,
            "source_digest_present": bool(fields.get("source_digest")),
            "seal_present": bool(fields.get("seal_present")),
            "export_present": bool(export_path),
            "verification_attached": command_result is not None,
        },
        "flywheel": {
            "verdict": verdict,
            "failure_code": failure_code,
            "dependency_node": {
                "id": f"buildc:{witness_id}",
                "local": verdict,
                "deps": [],
                "has_receipt": True,
                "criterion_version": 1,
            },
            "compatible_surfaces": [
                "harness.transitive_witness.DepNode",
                "harness.accountability_bench",
                "project-telos.model-foundry receipt chain",
            ],
        },
    }
    packet["packet_sha256"] = _canonical_hash(packet)
    return packet
