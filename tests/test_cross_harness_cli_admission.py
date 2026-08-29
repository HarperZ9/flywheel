from datetime import UTC, datetime, timedelta
import hashlib, json, pytest
from harness.cross_harness_artifacts import bind_attempt_receipt, canonical_sha256
from harness.cross_harness_cli import _apply_admission, _recheck_local_gate, main as cross_main
from harness.cross_harness_executor import SHARED_TOOL_POLICY

def _receipt_hash(row):
    body = {key: value for key, value in row.items() if key not in {"receipt_hash", "latency_ms"}}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
def test_local_phase_rechecks_bound_gate_and_emits_all_eight_sanitized_unavailable_rows(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    tasks = [{"task_id": f"agt-{n:03d}-full", "raw_prompt": f"p{n}", "raw_prompt_sha256": f"{n:064x}", "input_sha256s": {}, "required_inputs": [],
              "expected_artifacts": [], "oracle": {}} for n in (1, 3, 9, 10)]
    roles = ["local_14b", "local_32b"]
    manifest = {"schema": "harness.cross-harness-manifest/v1", "contract_schema": "harness.cross-harness-adapter-contract/v2", "task_set_id": "set", "task_rows": tasks, "provider_specs": [
        {"provider_role": role, "harness_id": "local_endpoint", "adapter_id": "openai_compatible_local/v1", "model_id": f"flywheel-local-coder-{role[-3:].lower()}", "model_display_name": role, "requested_model_reference": f"local:{role[-3:].upper()}"} for role in roles]}
    profiles = {"schema": "harness.model-endpoint-profiles/v1", "profiles": []}
    gate_rows, runtime_rows = [], []
    stale = (datetime.now(UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    for role, port in zip(roles, (8765, 8767)):
        model = role[-3:].upper(); profile = {"profile_id": f"serve-{model.lower()}", "model": model, "backend": "serve", "provider_role": "flywheel",
            "model_ref": f"local:{model}", "endpoint_url": f"http://127.0.0.1:{port}",
            "root_exists": True, "supports_agentic_workflow": True}
        profiles["profiles"].append(profile); profile_hash = canonical_sha256(profile)
        gate = {"schema": "harness.model-endpoint-gate.row/v1", "selected_profile_id": profile["profile_id"], "profile_sha256": profile_hash,
            "model": model, "backend": "serve", "expected_model_ref": profile["model_ref"], "observed_model_ref": profile["model_ref"],
            "health_ok": True, "generation_ok": True, "failure_class": "", "ollama_digest": "",
            "run_id": "gate-1", "observed_at": stale}
        gate["receipt_hash"] = _receipt_hash(gate); gate_rows.append(gate)
        runtime_rows.append({"provider_role": role, "focused_run_ready": True, "blocking_gates": [], "endpoint_profile_matches": [
                {"profile_id": profile["profile_id"], "model": model, "backend": "serve", "model_ref": profile["model_ref"], "profile_sha256": profile_hash,
                "root_exists": True, "supports_agentic_workflow": True}], "endpoint_gate_matches": []})
    gate = {"schema": "harness.model-endpoint-gate/v1", "run_id": "gate-1", "rows": gate_rows}
    for name, data in (("manifest.json", manifest), ("profiles.json", profiles), ("gate.json", gate)): (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    gate_sha = hashlib.sha256((tmp_path / "gate.json").read_bytes()).hexdigest()
    matrix = {"schema": "harness.adapter-runtime-matrix/v1", "endpoint_profiles_path": str(tmp_path / "profiles.json"),
        "endpoint_profiles_sha256": hashlib.sha256((tmp_path / "profiles.json").read_bytes()).hexdigest(), "endpoint_gate_path": str(tmp_path / "gate.json"), "endpoint_gate_sha256": gate_sha,
        "expected_gate_run_id": "gate-1", "runtime_rows": runtime_rows}
    (tmp_path / "matrix.json").write_text(json.dumps(matrix), encoding="utf-8")
    args = ["--manifest", str(tmp_path / "manifest.json"), "--runtime-matrix", str(tmp_path / "matrix.json"),
        "--artifact-root", str(tmp_path / "artifacts"), "--tasks", "agt-001,agt-003,agt-009,agt-010", "--roles", ",".join(roles), "--repetitions", "1",
        "--source-commit", "abc", "--source-root", str(source), "--phase", "local", "--timeout-seconds", "3", "--cache-state", "cold_declared",
        "--endpoint-gate", str(tmp_path / "gate.json"), "--gate-run-id", "gate-1", "--max-gate-age-seconds", "900",
        "--run-id", "local-run", "--strict-exit"]
    assert cross_main(args) == 1
    run = json.loads((tmp_path / "artifacts" / "local-run" / "run.json").read_text())
    scorecard = json.loads((tmp_path / "artifacts" / "local-run" / "scorecard.json").read_text()); comparison = json.loads((tmp_path / "artifacts" / "local-run" / "comparison-input.json").read_text())
    assert scorecard == comparison and scorecard["schema"] == "harness.cross-harness-task-scorecard/v1"
    assert "seed" not in scorecard and (tmp_path / "artifacts" / "local-run" / "artifact-index.json").is_file()
    assert len(run["rows"]) == 8 and all(row["execution_state"] == "unavailable" for row in run["rows"])
    for row in run["rows"]:
        evidence = row["availability_evidence"]
        assert evidence["blocking_gates"] == ["endpoint_gate_stale"]
        assert all(evidence[key] for key in ("role", "backend", "requested_model_reference", "observed_model_reference", "endpoint_profile_id", "endpoint_profile_sha256",
            "attempted_gate_path", "attempted_gate_sha256", "attempted_gate_run_id", "failure_reason"))
        assert "token" not in json.dumps(evidence).lower()
@pytest.mark.parametrize(("path", "value", "code"), [
    ("raw_prompt_sha256", "bad", "admission_prompt_mismatch"), ("input_sha256s", {"x": "bad"}, "admission_input_mismatch"),
    ("availability_evidence.adapter_evidence.oracle_spec_sha256", "bad", "admission_oracle_mismatch"), ("model_id", "bad", "admission_model_mismatch"), ("requested_model_reference", "bad", "admission_requested_model_mismatch"), ("model_observed", "bad", "admission_observed_model_mismatch"),
    ("adapter_id", "bad", "admission_adapter_mismatch"), ("tool_policy_sha256", "bad", "admission_policy_mismatch"),
    ("source_commit", "bad", "admission_source_mismatch"), ("source_snapshot_sha256", "bad", "admission_source_mismatch"), ("cache_state", "warm", "admission_cache_mismatch"),
    ("execution_mode", "bad", "admission_execution_mismatch"), ("task_set_id", "bad", "admission_execution_mismatch"),
])
def test_admission_binds_current_identity_and_blocks_only_affected_role(tmp_path, path, value, code):
    roles = ["codex_harness", "flywheel_harness"]
    tasks = [{"task_id": f"agt-00{i}-full", "raw_prompt_sha256": str(i) * 64, "input_sha256s": {}, "oracle": {"checker_id": str(i)}} for i in (1, 3)]
    manifest = {"task_set_id": "set", "task_rows": tasks, "provider_specs": [{"provider_role": role, "adapter_id": "adapter", "model_id": "model", "model_display_name": "Model", "requested_model_reference": "model"} for role in roles]}
    current = {"source_commit": "commit", "source_snapshot_sha256": "s" * 64, "cache_state": "cold_declared", "execution_mode": "focused_run"}
    rows = []
    for role in roles:
      for task in tasks:
        attempt = tmp_path / role / task["task_id"]; attempt.mkdir(parents=True); receipt = attempt / "receipt.json"
        row = {"phase": "admission-smoke", "provider_role": role, "task_id": task["task_id"], "repetition": 1,
            "primary_outcome": "completed", "receipt_path": str(receipt), "task_set_id": "set",
            "raw_prompt_sha256": task["raw_prompt_sha256"], "input_sha256s": {}, "adapter_id": "adapter", "model_id": "model", "model_display_name": "Model",
            "requested_model_reference": "model", "model_observed": "", "model_observation_basis": "unknown",
            "tool_policy_sha256": canonical_sha256(SHARED_TOOL_POLICY), **current,
            "availability_evidence": {"adapter_evidence": {"oracle_spec_sha256": canonical_sha256(task["oracle"])}}}
        if role == roles[1]:
            target, parts = row, path.split(".")
            for part in parts[:-1]: target = target[part]
            target[parts[-1]] = value; row["model_observation_basis"] = "structured_provider_event" if path == "model_observed" else row["model_observation_basis"]
        bind_attempt_receipt(row, {}, receipt); rows.append(row)
    admission = tmp_path / "admission.json"
    admission.write_text(json.dumps({"schema": "harness.cross-harness-run-receipt/v1", "phase": "admission-smoke", "rows": rows}), encoding="utf-8")
    matrix = {"runtime_rows": [{"provider_role": role, "focused_run_ready": True, "blocking_gates": []} for role in roles]}
    _apply_admission(matrix, admission, manifest, ["agt-009"], roles, 3, current=current)
    assert matrix["runtime_rows"][0]["focused_run_ready"] is True
    assert matrix["runtime_rows"][1]["blocking_gates"] == [code]
def test_missing_gate_or_admission_artifact_blocks_rows_instead_of_aborting(tmp_path):
    local = {"runtime_rows": [{"provider_role": "local_14b", "focused_run_ready": True, "blocking_gates": [], "endpoint_profile_matches": [{}]}], "endpoint_gate_sha256": "a" * 64}
    _recheck_local_gate(local, tmp_path / "missing-gate.json", "gate", ["local_14b"], datetime.now(UTC), 900)
    assert local["runtime_rows"][0]["blocking_gates"] == ["endpoint_gate_missing"]
    spark = {"runtime_rows": [{"provider_role": "codex_harness", "focused_run_ready": True,
                               "blocking_gates": []}]}
    _apply_admission(spark, tmp_path / "missing-admission.json", {"task_rows": []}, [], ["codex_harness"], 1)
    assert spark["runtime_rows"][0]["blocking_gates"] == ["admission_receipt_malformed"]
