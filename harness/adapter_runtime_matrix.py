"""Metadata-only adapter/runtime compatibility matrix."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = "harness.adapter-runtime-matrix/v1"
DEFAULT_CONTRACT = str(Path(__file__).resolve().parent.parent / "benchmarks" / "cross-harness-adapter-contract-v1.json")
GATE_FIELDS = (
    "selected_profile_id", "profile_sha256", "model", "backend",
    "expected_model_ref", "observed_model_ref", "health_ok", "generation_ok",
    "failure_class", "ollama_digest", "run_id", "observed_at",
)


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


def _canonical_sha256(value: dict[str, Any]) -> str:
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def build_matrix(
    contract: dict[str, Any], *, contract_path: str, contract_sha256: str,
    endpoint_profiles: dict[str, Any] | None = None, endpoint_profiles_path: str = "",
    endpoint_profiles_sha256: str = "", endpoint_gate: dict[str, Any] | None = None,
    endpoint_gate_path: str = "", endpoint_gate_sha256: str = "",
    endpoint_auth_status: dict[str, Any] | None = None, endpoint_auth_status_path: str = "",
    endpoint_auth_status_sha256: str = "", expected_gate_run_id: str = "",
    now: datetime | None = None, max_age_seconds: int = 900, run_id: str = "",
) -> dict[str, Any]:
    provider_rows = contract.get("provider_roles") if isinstance(contract.get("provider_roles"), list) else []
    current = now or datetime.now(UTC)
    rows = [
        _runtime_row(
            row, endpoint_profiles=endpoint_profiles or {}, endpoint_gate=endpoint_gate or {},
            endpoint_auth_status=endpoint_auth_status or {}, expected_gate_run_id=expected_gate_run_id,
            now=current, max_age_seconds=max_age_seconds,
        )
        for row in provider_rows if isinstance(row, dict)
    ]
    endpoint_blocked = lambda row: any(str(code).startswith("endpoint_gate") for code in row["blocking_gates"])
    return {
        "schema": SCHEMA, "timestamp_utc": now_utc(), "run_id": run_id,
        "status": "planned_not_executed", "contract_path": contract_path,
        "contract_sha256": contract_sha256, "endpoint_profiles_path": endpoint_profiles_path,
        "endpoint_profiles_sha256": endpoint_profiles_sha256, "endpoint_gate_path": endpoint_gate_path,
        "endpoint_gate_sha256": endpoint_gate_sha256, "expected_gate_run_id": expected_gate_run_id,
        "max_age_seconds": max_age_seconds, "endpoint_auth_status_path": endpoint_auth_status_path,
        "endpoint_auth_status_sha256": endpoint_auth_status_sha256,
        "secret_policy": "metadata-only; no provider calls; no endpoint probes; no token-store reads; env values are not emitted",
        "runtime_rows": rows,
        "summary": {
            "runtime_rows": len(rows),
            "provider_roles": sorted({str(row["provider_role"]) for row in rows if row["provider_role"]}),
            "manifest_ready_roles": sum(bool(row["manifest_ready"]) for row in rows),
            "focused_run_ready_roles": sum(bool(row["focused_run_ready"]) for row in rows),
            "endpoint_profile_ready_roles": sum(bool(row["endpoint_profile_ready"]) for row in rows),
            "auth_ready_roles": sum(bool(row["auth_ready"]) for row in rows),
            "roles_needing_discovery": sorted(row["provider_role"] for row in rows if "adapter_discovery" in row["blocking_gates"]),
            "roles_needing_endpoint_gate": sorted(row["provider_role"] for row in rows if endpoint_blocked(row)),
            "roles_needing_auth": sorted(row["provider_role"] for row in rows if "account_auth" in row["blocking_gates"]),
            "provider_execution": False, "endpoint_probe": False, "model_weight_read": False,
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
        "# Adapter runtime matrix", "", f"- Schema: `{matrix['schema']}`", f"- Status: `{matrix['status']}`",
        f"- Contract: `{matrix['contract_path']}`", f"- Endpoint profiles: `{matrix.get('endpoint_profiles_path', '')}`",
        f"- Endpoint gate: `{matrix.get('endpoint_gate_path', '')}`",
        f"- Endpoint auth status: `{matrix.get('endpoint_auth_status_path', '')}`",
        f"- Runtime rows: `{summary['runtime_rows']}`", f"- Manifest-ready roles: `{summary['manifest_ready_roles']}`",
        f"- Focused-run-ready roles: `{summary['focused_run_ready_roles']}`", "",
        "| Role | Harness | Target model | Adapter state | Manifest | Focused run | Blocking gates |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for row in matrix["runtime_rows"]:
        lines.append("| {provider_role} | {harness_id} | {target_model} | {adapter_state} | {manifest} | {focused} | {gates} |".format(
            **row, manifest=str(row["manifest_ready"]).lower(), focused=str(row["focused_run_ready"]).lower(),
            gates=", ".join(row["blocking_gates"])))
    lines.extend(["", "## Non-execution guards", ""] + [f"- {guard}" for guard in matrix["non_execution_guards"]])
    return "\n".join(lines) + "\n"


def _runtime_row(
    row: dict[str, Any], *, endpoint_profiles: dict[str, Any], endpoint_gate: dict[str, Any],
    endpoint_auth_status: dict[str, Any], expected_gate_run_id: str, now: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    role, target = str(row.get("provider_role", "")), str(row.get("target_model", ""))
    modes = [str(item) for item in row.get("allowed_modes", []) if item] if isinstance(row.get("allowed_modes"), list) else []
    profiles = _profile_matches(role, target, endpoint_profiles)
    auth = _auth_matches(role, endpoint_auth_status)
    needs_endpoint = role in {"local_14b", "local_32b"}
    needs_auth = role in {"codex_harness", "flywheel_harness", "claude_code"}
    profile_ready = any(item["root_exists"] and item["supports_agentic_workflow"] for item in profiles) if needs_endpoint else True
    gate_matches, gate_code = _endpoint_gate_result(profiles, endpoint_gate, expected_gate_run_id, now, max_age_seconds) if needs_endpoint else ([], "")
    auth_ready = any(item["configured"] for item in auth) if needs_auth else True
    blocking = []
    if str(row.get("adapter_state", "")) in {"needs_discovery", "needs_adapter"}:
        blocking.append("adapter_discovery")
    if needs_auth and not auth_ready:
        blocking.append("account_auth")
    if needs_endpoint and not profile_ready:
        blocking.append("endpoint_profile")
    if needs_endpoint and gate_code:
        blocking.append(gate_code)
    manifest_ready = "manifest_only" in modes
    focused_ready = "focused_run_after_approval" in modes and not blocking
    return {
        "schema": "harness.adapter-runtime-matrix.row/v1", "provider_role": role,
        "harness_id": str(row.get("harness_id", "")), "target_model": target,
        "adapter_state": str(row.get("adapter_state", "")), "allowed_modes": modes,
        "required_receipts": _strings(row.get("required_receipts")),
        "current_evidence": _strings(row.get("current_evidence")),
        "endpoint_profile_matches": profiles, "endpoint_profile_ready": profile_ready,
        "endpoint_gate_matches": gate_matches, "endpoint_gate_ready": needs_endpoint and not gate_code,
        "auth_matches": auth, "auth_ready": auth_ready, "manifest_ready": manifest_ready,
        "focused_run_ready": focused_ready, "blocking_gates": blocking,
        "non_execution": {"provider_execution": False, "endpoint_probe": False, "model_weight_read": False, "token_store_read": False},
    }


def _profile_matches(role: str, target: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = {"local_14b": "14B", "local_32b": "32B"}.get(role, target)
    rows = data.get("profiles") if isinstance(data.get("profiles"), list) else []
    return [{
        "profile_id": item.get("profile_id", ""), "model": item.get("model", ""),
        "backend": item.get("backend", ""), "provider_role": item.get("provider_role", ""),
        "model_ref": item.get("model_ref", ""), "profile_sha256": _canonical_sha256(item),
        "root_exists": bool(item.get("root_exists")),
        "supports_agentic_workflow": bool(item.get("supports_agentic_workflow")),
        "live_probed": bool(item.get("live_probed")),
    } for item in rows if isinstance(item, dict) and str(item.get("model", "")).lower() == wanted.lower()]


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if item] if isinstance(value, list) else []


def _auth_matches(role: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    provider = "codex" if role in {"codex_harness", "flywheel_harness"} else "claude" if role == "claude_code" else ""
    if not provider:
        return []
    lanes = data.get("lanes") if isinstance(data.get("lanes"), list) else []
    return [{
        "lane_id": lane.get("id", ""), "provider": lane.get("provider", ""),
        "mode": lane.get("mode", ""), "kind": lane.get("kind", ""),
        "configured": bool(lane.get("configured")), "evidence_basis": "cli_presence_only",
    } for lane in lanes if isinstance(lane, dict) and lane.get("provider") == provider and lane.get("kind") == "subscription_cli"]


def _parse_observed(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo and parsed.utcoffset() == UTC.utcoffset(parsed) else None
    except ValueError:
        return None


def _gate_failure(gate: dict[str, Any], profile: dict[str, Any], run_id: str, now: datetime, max_age: int) -> str:
    observed_raw = gate.get("observed_at")
    if observed_raw in {None, ""}:
        return "endpoint_gate_timestamp_missing"
    observed = _parse_observed(observed_raw)
    if observed is None:
        return "endpoint_gate_timestamp_invalid"
    age = (now.astimezone(UTC) - observed).total_seconds()
    if age < -30:
        return "endpoint_gate_from_future"
    if age > max_age:
        return "endpoint_gate_stale"
    if not run_id or gate.get("run_id") != run_id:
        return "endpoint_gate_run_mismatch"
    checks = (
        (gate.get("selected_profile_id") != profile["profile_id"], "endpoint_gate_profile_mismatch"),
        (gate.get("model") != profile["model"], "endpoint_gate_model_mismatch"),
        (gate.get("backend") != profile["backend"], "endpoint_gate_backend_mismatch"),
        (gate.get("profile_sha256") != profile["profile_sha256"], "endpoint_gate_profile_hash_mismatch"),
        (gate.get("expected_model_ref") != profile["model_ref"], "endpoint_gate_expected_ref_mismatch"),
        (gate.get("observed_model_ref") != profile["model_ref"], "endpoint_gate_observed_ref_mismatch"),
        (not gate.get("health_ok") or not gate.get("generation_ok") or bool(gate.get("failure_class")), "endpoint_gate_failed"),
        (profile["backend"].lower() == "ollama" and not gate.get("ollama_digest"), "endpoint_gate_ollama_digest_missing"),
    )
    return next((code for failed, code in checks if failed), "")


def _endpoint_gate_result(profiles, data, run_id, now, max_age):
    gates = data.get("rows") if isinstance(data.get("rows"), list) else []
    if not gates:
        return [], "endpoint_gate_missing"
    failures = []
    sanitized = []
    for profile in profiles:
        candidates = [gate for gate in gates if isinstance(gate, dict) and gate.get("selected_profile_id") == profile["profile_id"]]
        if not candidates:
            candidates = [gate for gate in gates if isinstance(gate, dict)]
        for gate in candidates:
            clean = {field: gate.get(field, "") for field in GATE_FIELDS}
            sanitized.append(clean)
            code = _gate_failure(gate, profile, run_id, now, max_age)
            if not code:
                return [clean], ""
            failures.append(code)
    return sanitized, failures[0] if failures else "endpoint_gate_missing"
