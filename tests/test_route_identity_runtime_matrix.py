import json
from datetime import UTC, datetime

import pytest

from harness.adapter_runtime_matrix import build_matrix
from scripts.run_model_endpoint_gate import build_report as build_gate_report


def _profile():
    return {"schema": "harness.model-endpoint-profile/v1", "profile_id": "ollama-release-14b", "model": "14B",
        "model_key": "14b", "backend": "ollama", "provider_role": "ollama_local",
        "model_ref": "ollama:flywheel-local-coder-14b", "root_exists": True, "supports_agentic_workflow": True,
        "endpoint_url": "http://127.0.0.1:11434", "selectors": ["flywheel-local-coder-14b"],
        "release_asset_sha256": "a" * 64, "expected_ollama_digest": "sha256:expected"}


def _contract(profile):
    return {"provider_roles": [{"provider_role": "local_14b", "harness_id": "local_endpoint", "model_id": "stable",
        "model_display_name": "Stable", "requested_model_reference": profile["model_ref"],
        "adapter_state": "needs_endpoint_profile_and_gate", "allowed_modes": ["manifest_only", "focused_run_after_approval"],
        "endpoint_selector": {"profile_id": profile["profile_id"], "backend": profile["backend"],
            "model_reference": profile["model_ref"], "release_asset_sha256": profile["release_asset_sha256"]}}]}


def _matrix(profiles, gate=None):
    selected = _profile()
    return build_matrix(_contract(selected), contract_path="contract.json", contract_sha256="hash",
        endpoint_profiles={"profiles": profiles}, endpoint_gate=gate, expected_gate_run_id="gate-run",
        now=datetime.now(UTC), run_id="matrix-run")["runtime_rows"][0]


def _producer_gate(tmp_path, digest):
    profile = _profile(); artifact = tmp_path / "profiles.json"
    artifact.write_text(json.dumps({"schema": "harness.model-endpoint-profiles/v1", "profiles": [profile]}), encoding="utf-8")
    def transport(_method, url, _body, _timeout):
        if url.endswith("/api/tags"):
            model = {"name": "flywheel-local-coder-14b"}
            if digest is not None: model["digest"] = digest
            return 200, {"models": [model]}
        raise AssertionError("generation must not run after a digest identity failure")
    return profile, build_gate_report(profile_artifact=str(artifact), models=[], backends=[],
                                      transport=transport, run_id="gate-run")


@pytest.mark.parametrize(("digest", "producer_code", "matrix_code"), [
    (None, "ollama_digest_missing", "endpoint_gate_ollama_digest_missing"),
    ("sha256:other", "ollama_digest_mismatch", "endpoint_gate_ollama_digest_mismatch"),
])
def test_matrix_preserves_typed_digest_failure_from_real_gate_producer(tmp_path, digest, producer_code, matrix_code):
    profile, gate = _producer_gate(tmp_path, digest)
    assert gate["rows"][0]["failure_class"] == producer_code
    row = _matrix([profile], gate)
    assert row["blocking_gates"] == [matrix_code]
    assert row["endpoint_gate_ready"] is False


@pytest.mark.parametrize("count", [0, 2])
def test_local_route_requires_exactly_one_profile_before_gate_evaluation(count):
    profiles = [_profile() for _ in range(count)]
    row = _matrix(profiles)
    assert row["blocking_gates"] == ["endpoint_profile_selection_mismatch"]
    assert row["endpoint_profile_ready"] is False
    assert row["endpoint_gate_ready"] is False
    assert row["focused_run_ready"] is False


def test_invalid_profile_cannot_report_a_skipped_gate_as_ready():
    profile = _profile(); profile["expected_ollama_digest"] = ""
    row = _matrix([profile])
    assert row["blocking_gates"] == ["endpoint_profile_ollama_digest_missing"]
    assert row["endpoint_gate_ready"] is False


def test_typed_digest_failure_does_not_mask_bound_profile_identity_drift(tmp_path):
    profile, gate = _producer_gate(tmp_path, None)
    gate["rows"][0]["profile_sha256"] = "drift"
    assert _matrix([profile], gate)["blocking_gates"] == ["endpoint_gate_profile_hash_mismatch"]
