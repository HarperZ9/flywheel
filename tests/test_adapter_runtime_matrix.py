import hashlib
import json
from datetime import UTC, datetime, timedelta
import pytest
from harness.adapter_runtime_matrix import build_matrix, render_markdown
from scripts.run_adapter_runtime_matrix import main as matrix_main
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
def test_exact_fresh_endpoint_gate_allows_local_focused_run():
    profiles = profile_fixture()
    row = local_row(matrix(profiles=profiles, gate=gate_fixture(profiles["profiles"][0])))
    assert row["endpoint_gate_ready"] is True
    assert row["focused_run_ready"] is True
    assert (row["model_observed"], row["model_observation_basis"]) == ("", "unknown")
    assert row["blocking_gates"] == []
    assert row["endpoint_gate_matches"] == [{
        "selected_profile_id": "serve-14b", "profile_sha256": canonical_sha256(profiles["profiles"][0]),
        "model": "14B", "backend": "serve", "expected_model_ref": "serve:expected",
        "observed_model_ref": "serve:expected", "health_ok": True, "generation_ok": True,
        "failure_class": "", "release_asset_sha256": "a" * 64, "expected_ollama_digest": "",
        "ollama_digest": "", "run_id": "gate-run",
        "observed_at": "2026-08-11T12:00:00Z",
    }]
def test_exact_32b_release_sha_and_digest_allow_local_focused_run():
    profile = profile_fixture(backend="ollama")["profiles"][0]
    profile.update(profile_id="ollama-release-32b", model="32B", model_key="32b",
        model_ref="ollama:flywheel-local-coder-32b",
        release_asset_sha256="65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4",
        expected_ollama_digest="sha256:35fa696e662eb83293491d4b87de1d1308254d82be7aa8244f4fa442bf0e09d9")
    contract = contract_fixture(profile); local = next(row for row in contract["provider_roles"] if row["provider_role"] == "local_14b")
    local.update(provider_role="local_32b", model_id="flywheel-local-coder-32b",
        requested_model_reference=profile["model_ref"]); local["endpoint_selector"]["release_asset_sha256"] = profile["release_asset_sha256"]
    result = build_matrix(contract, contract_path="contract.json", contract_sha256="hash", endpoint_profiles={"profiles": [profile]},
        endpoint_gate=gate_fixture(profile), expected_gate_run_id="gate-run", now=NOW); row = next(item for item in result["runtime_rows"] if item["provider_role"] == "local_32b")
    assert row["focused_run_ready"] is True and row["blocking_gates"] == []
@pytest.mark.parametrize(("mutate", "code"), [
    (lambda gate, profile: gate.update(rows=[]), "endpoint_gate_missing"),
    (lambda gate, profile: gate["rows"][0].update(health_ok=False, failure_class="endpoint_unavailable"), "endpoint_gate_failed"),
    (lambda gate, profile: gate["rows"][0].update(model="32B"), "endpoint_gate_model_mismatch"),
    (lambda gate, profile: gate["rows"][0].update(model="14b"), "endpoint_gate_model_mismatch"),
    (lambda gate, profile: gate["rows"][0].update(backend="ollama"), "endpoint_gate_backend_mismatch"),
    (lambda gate, profile: gate["rows"][0].update(backend="Serve"), "endpoint_gate_backend_mismatch"),
    (lambda gate, profile: gate["rows"][0].update(profile_sha256="bad"), "endpoint_gate_profile_hash_mismatch"),
    (lambda gate, profile: gate["rows"][0].update(observed_model_ref="serve:other"), "endpoint_gate_observed_ref_mismatch"),
])
def test_endpoint_identity_or_probe_mismatch_blocks_local_run(mutate, code):
    profiles = profile_fixture()
    gate = gate_fixture(profiles["profiles"][0])
    mutate(gate, profiles["profiles"][0])
    row = local_row(matrix(profiles=profiles, gate=gate))
    assert row["endpoint_gate_ready"] is False
    assert row["focused_run_ready"] is False
    assert row["blocking_gates"] == [code]


@pytest.mark.parametrize("digest", [True, False, 0, 1, [], {}, "   "])
def test_ollama_gate_requires_digest(digest):
    profiles = profile_fixture(backend="ollama")
    gate = gate_fixture(profiles["profiles"][0])
    gate["rows"][0]["ollama_digest"] = digest
    row = local_row(matrix(profiles=profiles, gate=gate))
    assert row["blocking_gates"] == ["endpoint_gate_ollama_digest_missing"]


@pytest.mark.parametrize(("mutate", "code"), [
    (lambda profile, gate: profile.update(release_asset_sha256="b" * 64), "endpoint_profile_release_asset_sha256_mismatch"),
    (lambda profile, gate: profile.update(expected_ollama_digest=""), "endpoint_profile_ollama_digest_missing"),
    (lambda profile, gate: gate["rows"][0].update(ollama_digest="sha256:other"), "endpoint_gate_ollama_digest_mismatch"),
])
def test_release_and_ollama_digest_identity_fail_closed(mutate, code):
    profiles = profile_fixture(backend="ollama"); gate = gate_fixture(profiles["profiles"][0])
    mutate(profiles["profiles"][0], gate)
    assert local_row(matrix(profiles=profiles, gate=gate))["blocking_gates"] == [code]


@pytest.mark.parametrize(("observed_at", "expected_run", "code"), [
    (None, "gate-run", "endpoint_gate_timestamp_missing"),
    ("not-a-time", "gate-run", "endpoint_gate_timestamp_invalid"),
    ((NOW + timedelta(seconds=31)).isoformat(), "gate-run", "endpoint_gate_from_future"),
    ((NOW - timedelta(seconds=901)).isoformat(), "gate-run", "endpoint_gate_stale"),
    (NOW.isoformat(), "different-run", "endpoint_gate_run_mismatch"),
])
def test_gate_freshness_and_run_identity_are_exact(observed_at, expected_run, code):
    profile = profile_fixture()["profiles"][0]
    gate = gate_fixture(profile)
    gate["rows"][0]["observed_at"] = observed_at

    row = local_row(matrix(gate=gate, expected_run=expected_run))

    assert row["blocking_gates"] == [code]


@pytest.mark.parametrize("observed_at", [[], {}, 123])
def test_non_string_gate_timestamp_is_invalid_without_raising(observed_at):
    profile = profile_fixture()["profiles"][0]
    gate = gate_fixture(profile)
    gate["rows"][0]["observed_at"] = observed_at
    assert local_row(matrix(gate=gate))["blocking_gates"] == ["endpoint_gate_timestamp_invalid"]


@pytest.mark.parametrize(("field", "value"), [
    ("health_ok", "false"),
    ("generation_ok", "false"),
    ("failure_class", False),
])
def test_malformed_probe_verdict_fields_fail_closed(field, value):
    profile = profile_fixture()["profiles"][0]
    gate = gate_fixture(profile)
    gate["rows"][0][field] = value
    assert local_row(matrix(gate=gate))["blocking_gates"] == ["endpoint_gate_failed"]


@pytest.mark.parametrize("field", ["root_exists", "supports_agentic_workflow"])
def test_string_false_profile_readiness_fields_block_local_run(field):
    profiles = profile_fixture()
    profiles["profiles"][0][field] = "false"
    gate = gate_fixture(profiles["profiles"][0])
    row = local_row(matrix(profiles=profiles, gate=gate))
    assert row["endpoint_profile_ready"] is False
    assert row["blocking_gates"] == ["endpoint_profile"]


def test_string_false_auth_configured_blocks_both_spark_roles():
    auth = auth_fixture()
    auth["lanes"][0]["configured"] = "false"
    spark = [row for row in matrix(auth=auth)["runtime_rows"]
             if row["provider_role"] in {"codex_harness", "flywheel_harness"}]
    assert all(row["auth_ready"] is False for row in spark)
    assert all(row["blocking_gates"] == ["account_auth"] for row in spark)


@pytest.mark.parametrize(("mutate", "code"), [
    (lambda gate: gate.update(schema="wrong"), "endpoint_gate_schema_mismatch"),
    (lambda gate: gate.update(run_id="other"), "endpoint_gate_run_mismatch"),
    (lambda gate: gate["rows"][0].update(run_id="other"), "endpoint_gate_run_mismatch"),
])
def test_gate_envelope_and_row_run_identity_are_required(mutate, code):
    profile = profile_fixture()["profiles"][0]
    gate = gate_fixture(profile)
    mutate(gate)
    assert local_row(matrix(gate=gate))["blocking_gates"] == [code]


def test_absent_endpoint_gate_remains_missing():
    assert local_row(matrix(gate=None))["blocking_gates"] == ["endpoint_gate_missing"]


@pytest.mark.parametrize("gate", [[], [{}], "not-an-object", 7])
def test_non_object_gate_envelope_is_schema_mismatch_without_raising(gate):
    assert local_row(matrix(gate=gate))["blocking_gates"] == ["endpoint_gate_schema_mismatch"]


def test_unrelated_gate_row_is_not_exposed_as_a_profile_match():
    profile = profile_fixture()["profiles"][0]
    gate = gate_fixture(profile)
    gate["rows"][0]["selected_profile_id"] = "other-profile"
    row = local_row(matrix(gate=gate))
    assert row["blocking_gates"] == ["endpoint_gate_profile_mismatch"]
    assert row["endpoint_gate_matches"] == []


def test_duplicate_rows_for_selected_profile_fail_deterministically():
    profile = profile_fixture()["profiles"][0]
    gate = gate_fixture(profile)
    gate["rows"].append(dict(gate["rows"][0]))
    row = local_row(matrix(gate=gate))
    assert row["blocking_gates"] == ["endpoint_gate_duplicate_profile"]
    assert row["endpoint_gate_matches"] == []


@pytest.mark.parametrize("offset", [-30, 900])
def test_gate_freshness_boundaries_are_inclusive(offset):
    profile = profile_fixture()["profiles"][0]
    gate = gate_fixture(profile, observed_at=(NOW - timedelta(seconds=offset)).isoformat())
    assert local_row(matrix(gate=gate))["endpoint_gate_ready"] is True


def test_empty_expected_and_observed_run_ids_do_not_match():
    profile = profile_fixture()["profiles"][0]
    gate = gate_fixture(profile, run_id="")
    assert local_row(matrix(gate=gate, expected_run=""))["blocking_gates"] == ["endpoint_gate_run_mismatch"]


def test_both_spark_roles_require_codex_cli_presence_only():
    result = matrix(gate=None, auth=auth_fixture(configured=False))
    spark = [row for row in result["runtime_rows"] if row["provider_role"] in {"codex_harness", "flywheel_harness"}]

    assert all(row["blocking_gates"] == ["account_auth"] for row in spark)
    assert all(row["auth_matches"][0]["evidence_basis"] == "cli_presence_only" for row in spark)
    assert all("path" not in row["auth_matches"][0] for row in spark)


def test_manifest_mode_alone_never_implies_focused_readiness():
    dry = next(row for row in matrix()["runtime_rows"] if row["provider_role"] == "dry")
    assert dry["manifest_ready"] is True
    assert dry["focused_run_ready"] is False


def test_matrix_records_gate_metadata_and_renders_guards():
    result = matrix(gate=gate_fixture(profile_fixture()["profiles"][0]))
    assert result["endpoint_gate_path"] == "gate.json"
    assert result["endpoint_gate_sha256"] == "gate-hash"
    assert result["expected_gate_run_id"] == "gate-run"
    assert result["max_age_seconds"] == 900
    assert "must not call Codex" in render_markdown(result)

def cli_matrix(tmp_path, gate):
    contract_path = tmp_path / "contract.json"
    profiles_path = tmp_path / "profiles.json"
    gate_path = tmp_path / "gate.json"
    out = tmp_path / "matrix.json"
    profiles = profile_fixture()
    contract_path.write_text(json.dumps(contract_fixture(profiles["profiles"][0])), encoding="utf-8")
    profiles_path.write_text(json.dumps(profiles), encoding="utf-8")
    args = [
        "--contract", str(contract_path), "--endpoint-profiles", str(profiles_path),
        "--endpoint-gate-run-id", "gate-run", "--endpoint-gate-max-age-seconds", "600",
        "--out", str(out), "--markdown-out", ""]
    if gate != "omitted":
        if gate != "missing":
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
        args.extend(["--endpoint-gate", str(gate_path)])
    assert matrix_main(args) == 0
    return json.loads(out.read_text(encoding="utf-8")), gate_path
def test_metadata_cli_reads_gate_and_records_path_hash_run_and_age(tmp_path):
    profile = profile_fixture()["profiles"][0]
    gate = gate_fixture(profile, observed_at=datetime.now(UTC).isoformat())
    result, gate_path = cli_matrix(tmp_path, gate)
    assert result["endpoint_gate_path"] == str(gate_path)
    assert result["endpoint_gate_sha256"] == hashlib.sha256(gate_path.read_bytes()).hexdigest()
    assert result["expected_gate_run_id"] == "gate-run"
    assert result["max_age_seconds"] == 600
    assert result["summary"]["endpoint_probe"] is False
    assert result["summary"]["token_store_read"] is False
@pytest.mark.parametrize(("gate", "code"), [
    ("omitted", "endpoint_gate_missing"), ("missing", "endpoint_gate_missing"),
    ({}, "endpoint_gate_schema_mismatch"), ([], "endpoint_gate_schema_mismatch"),
])
def test_cli_preserves_missing_and_malformed_gate_evidence(tmp_path, gate, code):
    result, _ = cli_matrix(tmp_path, gate)
    assert local_row(result)["blocking_gates"] == [code]
