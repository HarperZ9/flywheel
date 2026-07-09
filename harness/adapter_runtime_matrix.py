"""Metadata-only adapter/runtime compatibility matrix."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = "harness.adapter-runtime-matrix/v1"
DEFAULT_CONTRACT = "C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json"


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_matrix(
    contract: dict[str, Any],
    *,
    contract_path: str,
    contract_sha256: str,
    endpoint_profiles: dict[str, Any] | None = None,
    endpoint_profiles_path: str = "",
    endpoint_profiles_sha256: str = "",
    endpoint_auth_status: dict[str, Any] | None = None,
    endpoint_auth_status_path: str = "",
    endpoint_auth_status_sha256: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    provider_rows = contract.get("provider_roles") if isinstance(contract.get("provider_roles"), list) else []
    endpoint_profiles = endpoint_profiles or {}
    endpoint_auth_status = endpoint_auth_status or {}
    rows = [
        _runtime_row(row, endpoint_profiles=endpoint_profiles, endpoint_auth_status=endpoint_auth_status)
        for row in provider_rows
        if isinstance(row, dict)
    ]
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "run_id": run_id,
        "status": "planned_not_executed",
        "contract_path": contract_path,
        "contract_sha256": contract_sha256,
        "endpoint_profiles_path": endpoint_profiles_path,
        "endpoint_profiles_sha256": endpoint_profiles_sha256,
        "endpoint_auth_status_path": endpoint_auth_status_path,
        "endpoint_auth_status_sha256": endpoint_auth_status_sha256,
        "secret_policy": "metadata-only; no provider calls; no endpoint probes; no token-store reads; env values are not emitted",
        "runtime_rows": rows,
        "summary": {
            "runtime_rows": len(rows),
            "provider_roles": sorted({str(row.get("provider_role", "")) for row in rows if row.get("provider_role")}),
            "manifest_ready_roles": sum(1 for row in rows if row.get("manifest_ready")),
            "focused_run_ready_roles": sum(1 for row in rows if row.get("focused_run_ready")),
            "endpoint_profile_ready_roles": sum(1 for row in rows if row.get("endpoint_profile_ready")),
            "auth_ready_roles": sum(1 for row in rows if row.get("auth_ready")),
            "roles_needing_discovery": sorted({
                str(row.get("provider_role", ""))
                for row in rows
                if "adapter_discovery" in row.get("blocking_gates", [])
            }),
            "roles_needing_endpoint_gate": sorted({
                str(row.get("provider_role", ""))
                for row in rows
                if "endpoint_gate" in row.get("blocking_gates", [])
            }),
            "roles_needing_auth": sorted({
                str(row.get("provider_role", ""))
                for row in rows
                if "account_auth" in row.get("blocking_gates", [])
            }),
            "provider_execution": False,
            "endpoint_probe": False,
            "model_weight_read": False,
            "token_store_read": False,
        },
        "non_execution_guards": [
            "The matrix may read only metadata artifacts supplied by path.",
            "The matrix must not call Codex, Claude Code, OpenCode, Flywheel, serve, Ollama, or provider APIs.",
            "The matrix must not read model weights, token stores, .env files, API keys, or credential values.",
            "A manifest-ready adapter is not an executed benchmark result.",
        ],
    }


def render_markdown(matrix: dict[str, Any]) -> str:
    summary = matrix["summary"]
    lines = [
        "# Adapter runtime matrix",
        "",
        f"- Schema: `{matrix['schema']}`",
        f"- Status: `{matrix['status']}`",
        f"- Contract: `{matrix['contract_path']}`",
        f"- Endpoint profiles: `{matrix.get('endpoint_profiles_path', '')}`",
        f"- Endpoint auth status: `{matrix.get('endpoint_auth_status_path', '')}`",
        f"- Runtime rows: `{summary['runtime_rows']}`",
        f"- Manifest-ready roles: `{summary['manifest_ready_roles']}`",
        f"- Focused-run-ready roles: `{summary['focused_run_ready_roles']}`",
        "",
        "| Role | Harness | Target model | Adapter state | Manifest | Focused run | Blocking gates |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in matrix["runtime_rows"]:
        lines.append(
            "| {role} | {harness} | {model} | {state} | {manifest} | {focused} | {gates} |".format(
                role=row.get("provider_role", ""),
                harness=row.get("harness_id", ""),
                model=row.get("target_model", ""),
                state=row.get("adapter_state", ""),
                manifest=str(row.get("manifest_ready", False)).lower(),
                focused=str(row.get("focused_run_ready", False)).lower(),
                gates=", ".join(row.get("blocking_gates", [])),
            )
        )
    lines.extend(["", "## Non-execution guards", ""])
    for guard in matrix["non_execution_guards"]:
        lines.append(f"- {guard}")
    return "\n".join(lines) + "\n"


def _runtime_row(
    row: dict[str, Any],
    *,
    endpoint_profiles: dict[str, Any],
    endpoint_auth_status: dict[str, Any],
) -> dict[str, Any]:
    provider_role = str(row.get("provider_role", ""))
    target_model = str(row.get("target_model", ""))
    harness_id = str(row.get("harness_id", ""))
    adapter_state = str(row.get("adapter_state", ""))
    allowed_modes = [str(item) for item in row.get("allowed_modes", []) if item] if isinstance(row.get("allowed_modes"), list) else []
    profile_matches = _endpoint_profile_matches(provider_role, target_model, endpoint_profiles)
    auth_matches = _auth_matches(provider_role, endpoint_auth_status)
    needs_endpoint = provider_role in {"local_14b", "local_32b"}
    needs_auth = provider_role in {"codex_harness", "claude_code"}
    needs_discovery = adapter_state in {"needs_discovery", "needs_adapter"}
    endpoint_profile_ready = any(
        bool(match.get("root_exists")) and bool(match.get("supports_agentic_workflow"))
        for match in profile_matches
    ) if needs_endpoint else True
    endpoint_gate_ready = False
    auth_ready = bool(auth_matches and any(match.get("configured") for match in auth_matches)) if needs_auth else True
    manifest_ready = "manifest_only" in allowed_modes
    blocking_gates = []
    if needs_discovery:
        blocking_gates.append("adapter_discovery")
    if needs_auth and not auth_ready:
        blocking_gates.append("account_auth")
    if needs_endpoint and not endpoint_profile_ready:
        blocking_gates.append("endpoint_profile")
    if needs_endpoint and not endpoint_gate_ready:
        blocking_gates.append("endpoint_gate")
    focused_run_ready = manifest_ready and not blocking_gates
    return {
        "schema": "harness.adapter-runtime-matrix.row/v1",
        "provider_role": provider_role,
        "harness_id": harness_id,
        "target_model": target_model,
        "adapter_state": adapter_state,
        "allowed_modes": allowed_modes,
        "required_receipts": [str(item) for item in row.get("required_receipts", []) if item]
        if isinstance(row.get("required_receipts"), list)
        else [],
        "current_evidence": [str(item) for item in row.get("current_evidence", []) if item]
        if isinstance(row.get("current_evidence"), list)
        else [],
        "endpoint_profile_matches": profile_matches,
        "endpoint_profile_ready": endpoint_profile_ready,
        "endpoint_gate_ready": endpoint_gate_ready,
        "auth_matches": auth_matches,
        "auth_ready": auth_ready,
        "manifest_ready": manifest_ready,
        "focused_run_ready": focused_run_ready,
        "blocking_gates": blocking_gates,
        "non_execution": {
            "provider_execution": False,
            "endpoint_probe": False,
            "model_weight_read": False,
            "token_store_read": False,
        },
    }


def _endpoint_profile_matches(provider_role: str, target_model: str, endpoint_profiles: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = endpoint_profiles.get("profiles") if isinstance(endpoint_profiles.get("profiles"), list) else []
    if provider_role == "local_14b":
        model = "14B"
    elif provider_role == "local_32b":
        model = "32B"
    else:
        model = target_model
    matches = []
    for profile in profiles:
        if not isinstance(profile, dict) or str(profile.get("model", "")).lower() != model.lower():
            continue
        matches.append({
            "profile_id": profile.get("profile_id", ""),
            "model": profile.get("model", ""),
            "backend": profile.get("backend", ""),
            "provider_role": profile.get("provider_role", ""),
            "root_exists": bool(profile.get("root_exists")),
            "supports_agentic_workflow": bool(profile.get("supports_agentic_workflow")),
            "live_probed": bool(profile.get("live_probed")),
        })
    return matches


def _auth_matches(provider_role: str, endpoint_auth_status: dict[str, Any]) -> list[dict[str, Any]]:
    lanes = endpoint_auth_status.get("lanes") if isinstance(endpoint_auth_status.get("lanes"), list) else []
    if provider_role == "codex_harness":
        provider = "codex"
    elif provider_role == "claude_code":
        provider = "claude"
    else:
        return []
    return [
        {
            "lane_id": lane.get("id", ""),
            "provider": lane.get("provider", ""),
            "mode": lane.get("mode", ""),
            "kind": lane.get("kind", ""),
            "configured": bool(lane.get("configured")),
        }
        for lane in lanes
        if isinstance(lane, dict) and lane.get("provider") == provider
    ]
