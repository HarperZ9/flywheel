"""Shared fixtures for the adapter runtime matrix tests.

Lifted out of tests/test_adapter_runtime_matrix.py when that file reached the
repository's 300-line ceiling, so coverage could keep growing without either
dropping an assertion or raising the gate. No test lives here; every function
builds an input document the tests then mutate.
"""
import hashlib
import json
from datetime import UTC, datetime

from harness.adapter_runtime_matrix import build_matrix
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
def canonical_sha256(value):
    body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
def contract_fixture(selector):
    def row(role, harness, model, state="contract_only", modes=None):
        return {
            "provider_role": role, "harness_id": harness, "model_id": model,
            "model_display_name": model, "requested_model_reference": model,
            "adapter_state": state,
            "allowed_modes": modes or ["manifest_only", "focused_run_after_approval"],
            "required_receipts": [],
        }
    local = row("local_14b", "local_endpoint", "flywheel-local-coder-14b", "needs_endpoint_profile_and_gate")
    local["endpoint_selector"] = {key: selector[key] for key in ("profile_id", "backend", "model_ref")}
    local["endpoint_selector"]["model_reference"] = local["endpoint_selector"].pop("model_ref")
    local["endpoint_selector"]["release_asset_sha256"] = "a" * 64
    return {"provider_roles": [
        row("codex_harness", "codex", "5.3-Codex-Spark"),
        row("flywheel_harness", "flywheel", "5.3-Codex-Spark"),
        local,
        row("dry", "dry_null", "none", modes=["manifest_only"]),
    ]}
def profile_fixture(*, backend="serve"):
    profile = {
        "profile_id": f"{backend}-14b", "model": "14B", "model_key": "14b",
        "backend": backend, "provider_role": "flywheel", "root_exists": True,
        "supports_agentic_workflow": True,
        "model_ref": "serve:expected" if backend == "serve" else "ollama:qwen:14b",
        "release_asset_sha256": "a" * 64, "expected_ollama_digest": "sha256:abc" if backend == "ollama" else "",
    }
    if backend == "ollama":
        profile["selectors"] = ["qwen:14b"]
    return {"profiles": [profile]}
def auth_fixture(*, configured=True):
    return {"lanes": [{
        "id": "codex_subscription", "provider": "codex", "mode": "plan",
        "kind": "subscription_cli", "configured": configured,
        "evidence": {"path": "operator://codex-cli", "found": configured},
    }]}
def gate_fixture(profile, *, observed_at=None, run_id="gate-run"):
    return {"schema": "harness.model-endpoint-gate/v1", "run_id": run_id, "rows": [{
        "selected_profile_id": profile["profile_id"], "profile_sha256": canonical_sha256(profile),
        "model": profile["model"], "backend": profile["backend"],
        "expected_model_ref": profile["model_ref"], "observed_model_ref": profile["model_ref"],
        "health_ok": True, "generation_ok": True, "failure_class": "",
        "ollama_digest": profile["expected_ollama_digest"] if profile["backend"] == "ollama" else "",
        "release_asset_sha256": profile["release_asset_sha256"], "expected_ollama_digest": profile["expected_ollama_digest"],
        "run_id": run_id, "observed_at": observed_at or NOW.isoformat().replace("+00:00", "Z"),
    }]}
def matrix(*, profiles=None, gate=None, auth=None, now=NOW, expected_run="gate-run", max_age=900):
    profiles = profiles or profile_fixture()
    return build_matrix(
        contract_fixture(profiles["profiles"][0]), contract_path="contract.json", contract_sha256="contract-hash",
        endpoint_profiles=profiles, endpoint_gate=gate,
        endpoint_gate_path="gate.json" if gate else "", endpoint_gate_sha256="gate-hash" if gate else "",
        endpoint_auth_status=auth or auth_fixture(), expected_gate_run_id=expected_run,
        now=now, max_age_seconds=max_age, run_id="matrix-run",
    )
def local_row(result):
    return next(row for row in result["runtime_rows"] if row["provider_role"] == "local_14b")