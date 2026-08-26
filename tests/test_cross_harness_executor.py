import hashlib
import json
from pathlib import Path
import pytest
from harness.cross_harness_executor import (
    SHARED_TOOL_POLICY,
    comparison_key,
    derive_primary_outcome,
    execute_cross_harness_manifest,
    expand_attempt_rows,
    resolve_task_ids,
)
from harness.cross_harness_types import (
    AdapterResult, AttemptRequest, AvailabilityResult, CrossHarnessAdapter, EnforcementResult,
)
TASKS = [
    {"task_id": "agt-001-index-fallback-integrity"},
    {"task_id": "agt-003-codex-flywheel-shared-task"},
    {"task_id": "agt-010-documentation-schematic-maintenance"},
]
def test_typed_request_and_declared_policy_are_exact():
    request = AttemptRequest(
        "run", "spark", "set", "agt-001-index-fallback-integrity", "prompt", "a" * 64,
        "codex_harness", "codex", "codex_cli_json/v1", "spark", "spark", Path("work"), "b" * 64,
        {"input.json": "c" * 64}, SHARED_TOOL_POLICY, "d" * 64, 1, "cold_declared", 30, Path("out"),
    )
    assert request.provider_role == "codex_harness"
    assert isinstance(CrossHarnessAdapter, type)
    assert SHARED_TOOL_POLICY == {
        "version": "cross-harness-read-only/v1", "allow_read": True,
        "allow_write": False, "allow_exec": False, "allow_mcp": False,
        "max_steps": 6, "max_output_tokens": 2048,
    }
def test_selectors_resolve_exact_or_unique_short_and_reject_zero_or_many():
    assert resolve_task_ids(TASKS, ["agt-003", TASKS[0]["task_id"]]) == [
        "agt-003-codex-flywheel-shared-task", "agt-001-index-fallback-integrity"
    ]
    with pytest.raises(ValueError, match="unknown task selector"):
        resolve_task_ids(TASKS, ["agt-999"])
    with pytest.raises(ValueError, match="ambiguous task selector"):
        resolve_task_ids(TASKS + [{"task_id": "agt-001-another"}], ["agt-001"])
@pytest.mark.parametrize(("axes", "outcome", "status"), [
    (("unavailable", "not_run", "not_emitted"), "unavailable", "skipped"),
    (("timeout", "not_run", "not_emitted"), "timeout", "failed"),
    (("internal_error", "not_run", "not_emitted"), "internal_error", "failed"),
    (("malformed", "not_run", "not_emitted"), "malformed", "failed"),
    (("returned", "pass", "drift"), "receipt_drift", "invalid"),
    (("returned", "unverifiable", "verified"), "unverifiable", "executed"),
    (("returned", "fail", "verified"), "oracle_fail", "executed"),
    (("returned", "pass", "verified"), "completed", "executed"),
])
def test_primary_outcome_precedence_keeps_axes_orthogonal(axes, outcome, status):
    assert derive_primary_outcome(*axes) == (outcome, status)
@pytest.mark.parametrize("axes", [
    ("bogus", "not_run", "not_emitted"),
    ("returned", "bogus", "verified"),
    ("returned", "pass", "bogus"),
    ("returned", "pass", "not_emitted"),
    ("launched", "not_run", "not_emitted"),
])
def test_primary_outcome_rejects_invalid_or_inconsistent_axes(axes):
    with pytest.raises(ValueError, match="state"):
        derive_primary_outcome(*axes)
def test_comparison_key_uses_declared_policy_not_actual_enforcement():
    row = {"task_set_id": "set", "task_id": "task", "raw_prompt_sha256": "a" * 64,
           "tool_policy_sha256": "b" * 64, "execution_mode": "focused_run",
           "enforcement_sha256": "c" * 64, "input_sha256s": {"z": "d" * 64},
           "model_id": "Spark", "requested_model_reference": "5.3-Codex-Spark", "cache_state": "cold_declared", "phase": "spark",
           "source_snapshot_sha256": "e" * 64, "workspace_snapshot_sha256": "f" * 64,
           "provider_role": "codex_harness", "repetition": 1}
    key = comparison_key(row)
    assert isinstance(key, str) and len(key) == 64
    assert comparison_key({**row, "provider_role": "flywheel_harness", "repetition": 3,
                           "enforcement_sha256": "0" * 64}) == key
    for field in ("task_id", "input_sha256s", "model_id", "requested_model_reference", "cache_state", "phase",
                  "source_snapshot_sha256", "workspace_snapshot_sha256"):
        assert comparison_key({**row, field: "changed"}) != key
    local = {**row, "availability_evidence": {"endpoint_profile_id": "release-14b", "endpoint_profile_sha256": "1" * 64,
             "release_asset_sha256": "2" * 64, "expected_ollama_digest": "sha256:expected", "observed_ollama_digest": "sha256:expected"}}
    local_key = comparison_key(local)
    for field in ("endpoint_profile_id", "endpoint_profile_sha256", "release_asset_sha256", "expected_ollama_digest", "observed_ollama_digest"):
        evidence = {**local["availability_evidence"], field: "changed"}
        assert comparison_key({**local, "availability_evidence": evidence}) != local_key
def _manifest(roles):
    tasks = [{"task_id": f"agt-{n:03d}-task", "raw_prompt": f"prompt-{n}",
              "raw_prompt_sha256": f"{n:064x}", "input_sha256s": {},
              "required_inputs": [], "expected_artifacts": [], "oracle": {}}
             for n in (1, 3, 9, 10)]
    return {"task_set_id": "set", "task_rows": tasks,
            "provider_specs": [{"provider_role": role, "harness_id": role.split("_")[0],
                                "adapter_id": f"{role}/v1", "model_id": role, "model_display_name": role, "requested_model_reference": role}
                               for role in roles]}
def _runtime(roles, *, ready=True):
    return {"endpoint_gate_path": "gate.json", "endpoint_gate_sha256": "e" * 64,
            "expected_gate_run_id": "gate-run", "runtime_rows": [
                {"provider_role": role, "focused_run_ready": ready,
                 "blocking_gates": [] if ready else ["endpoint_gate_stale"],
                 "endpoint_profile_matches": [{"profile_id": role, "backend": "serve",
                                                "model_ref": f"serve:{role}", "profile_sha256": "f" * 64}],
                 "endpoint_gate_matches": []}
                for role in roles]}
@pytest.mark.parametrize(("roles", "repetitions", "count"), [
    (["codex_harness", "flywheel_harness"], 3, 24),
    (["local_14b", "local_32b"], 1, 8),
])
def test_expansion_has_exact_count_and_unique_run_phase_attempt_keys(tmp_path, roles, repetitions, count):
    rows = expand_attempt_rows(_manifest(roles), _runtime(roles), artifact_root=tmp_path,
                               run_id="run-1", phase="spark", selectors=["agt-001", "agt-003", "agt-009", "agt-010"],
                               roles=roles, repetitions=repetitions)
    assert len(rows) == count
    assert len({tuple(row["attempt_key"]) for row in rows}) == count
    assert len({row["attempt_dir"] for row in rows}) == count
    assert all(Path(row["attempt_dir"]).parts[-5:] ==
               ("run-1", "spark", row["provider_role"], row["task_id"], f"rep-{row['repetition']:03d}")
               for row in rows)
def test_expansion_rejects_duplicate_attempt_keys(tmp_path):
    with pytest.raises(ValueError, match="duplicate attempt key"):
        expand_attempt_rows(_manifest(["local_14b"]), _runtime(["local_14b"]), artifact_root=tmp_path,
                            run_id="run", phase="local", selectors=["agt-001"],
                            roles=["local_14b", "local_14b"], repetitions=1)
class FakeAdapter:
    role = "local_14b"
    adapter_id = "local_14b/v1"
    def __init__(self, *, available=True, result=None):
        self.available, self.result, self.calls = available, result, []
    def enforcement(self, request):
        self.calls.append("enforcement")
        description = {"boundary": "fake-read-only"}
        return EnforcementResult(description, canonical_hash(description), "verified_live_and_fixture", "equivalent")
    def availability(self, request):
        self.calls.append("availability")
        return AvailabilityResult(self.available, "" if self.available else "endpoint_unavailable",
                                  "ready" if self.available else "offline", {"probe": "fixture"})
    def execute(self, request):
        self.calls.append("execute")
        if isinstance(self.result, Exception): raise self.result
        return self.result
class SecretEnforcementAdapter(FakeAdapter):
    def enforcement(self, request):
        return EnforcementResult({"authorization_token": "never-write-me"}, "x" * 64, "described", "non_equivalent")
def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _one_task(source, *, expected=(), oracle=None, inputs=(), task_id="agt-001-task"):
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in inputs}
    return {"task_set_id": "set", "task_rows": [{"task_id": task_id, "raw_prompt": "prompt\n",
             "raw_prompt_sha256": hashlib.sha256(b"prompt\n").hexdigest(), "input_sha256s": hashes,
             "required_inputs": list(inputs), "expected_artifacts": list(expected), "oracle": oracle or {}}],
            "provider_specs": [{"provider_role": "local_14b", "harness_id": "local_endpoint",
                                "adapter_id": "local_14b/v1", "model_id": "flywheel-local-coder-14b", "model_display_name": "Local 14B", "requested_model_reference": "serve:local_14b"}]}


def test_unavailable_row_hashes_enforcement_first_and_preserves_gate_evidence_and_workspace(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    runtime = _runtime(["local_14b"], ready=False)
    adapter = FakeAdapter()
    run = execute_cross_harness_manifest(
        _one_task(source), runtime, {"local_14b": adapter}, artifact_root=tmp_path / "artifacts",
        source_root=source, run_id="run", phase="local", selectors=["agt-001"],
        roles=["local_14b"], repetitions=1,
    )
    row = run["rows"][0]
    assert adapter.calls == ["enforcement"]
    assert (row["execution_state"], row["status"], row["primary_outcome"]) == ("unavailable", "skipped", "unavailable")
    assert row["policy_equivalence"] == "non_equivalent"
    assert (row["enforcement_verification_state"], row["adapter_verification_claim"]) == ("unverified", "verified_live_and_fixture")
    assert row["enforcement_sha256"] == canonical_hash({"boundary": "fake-read-only"})
    assert row["availability_evidence"]["blocking_gates"] == ["endpoint_gate_stale"]
    assert row["availability_evidence"]["requested_model_reference"] == "serve:local_14b"
    assert Path(row["workspace_root"]).is_dir()
    assert (row["planned"], row["admitted"], row["blocked"], row["launched"]) == (True, False, True, False) and row["metric_null_reasons"]


def test_returned_unverifiable_attempt_rechecks_receipt_and_preserves_workspace(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    result = AdapterResult("returned", '{"artifacts":{"result.json":{}}}', [{"authorization_token": "hide", "event": "read"}], 7, "14B", "seeded", "", "",
                           {"memory": None}, {"tokens": None}, ["read"], [], "structured_provider_response")
    run = execute_cross_harness_manifest(
        _one_task(source, expected=("result.json",), oracle={"expected_artifacts": ["result.json"]}),
        _runtime(["local_14b"]), {"local_14b": FakeAdapter(result=result)},
        artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="local",
        selectors=["agt-001"], roles=["local_14b"], repetitions=1,
    )
    row = run["rows"][0]
    assert (row["execution_state"], row["oracle_state"], row["receipt_state"]) == ("returned", "unverifiable", "verified")
    assert row["primary_outcome"] == "unverifiable" and row["status"] == "executed"
    assert row["availability_evidence"]["adapter_evidence"] == {"probe": "fixture"}
    assert Path(row["workspace_root"]).is_dir()
    assert len(row["comparison_key"]) == 64 and row["source_commit"] == "unverified"
    assert {(Path(row["attempt_dir"]) / name).is_file() for name in ("oracle.json", "resource.json")} == {True} and "hide" not in Path(row["tool_trace_path"]).read_text()
    index = json.loads((tmp_path / "artifacts" / "run" / "artifact-index.json").read_text())
    assert all(item["path"] != "artifact-index.json" for item in index["artifacts"])
    assert run["source_snapshot_before"] == run["source_snapshot_after"]


def test_successful_attempt_cleans_workspace_only_after_oracle_and_receipt_rechecks(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    fixture = {"events": [
        {"event_id": "e1", "type": "mcp_call", "outcome": "failure"},
        {"event_id": "e2", "type": "artifact_read", "source": "stale", "before_sha256": "1", "after_sha256": "1"},
        {"event_id": "e3", "type": "json_parse", "outcome": "failure"},
        {"event_id": "e4", "type": "match", "mode": "degraded"},
    ]}
    (source / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")
    input_hash = hashlib.sha256((source / "fixture.json").read_bytes()).hexdigest()
    report = {"task_id": "agt-001-index-fallback-integrity", "input_sha256s": {"fixture.json": input_hash},
              "failure_classes": ["degraded_match", "invalid_json", "live_mcp_failure", "stale_artifact_use"],
              "cited_event_ids": ["e1", "e2", "e3", "e4"],
              "receipt_input_sha256s": {"fixture.json": input_hash}, "mcp_healthy": False}
    output = json.dumps({"artifacts": {"report.json": report,
                                       "report.md": "# agt-001-index-fallback-integrity\n"}})
    result = AdapterResult("returned", output, [], 1, "14B", "seeded", "", "", {}, {}, [], [], "structured_provider_response")
    manifest = _one_task(source, task_id="agt-001-index-fallback-integrity",
                         expected=("report.json", "report.md"), inputs=("fixture.json",),
                         oracle={"checker_id": "index_fallback_integrity/v1", "fixture": "fixture.json",
                                 "expected_artifacts": ["report.json", "report.md"]})
    run = execute_cross_harness_manifest(
        manifest, _runtime(["local_14b"]), {"local_14b": FakeAdapter(result=result)},
        artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="local",
        selectors=["agt-001"], roles=["local_14b"], repetitions=1)
    row = run["rows"][0]
    assert (row["primary_outcome"], row["receipt_state"]) == ("completed", "verified")
    assert not Path(row["workspace_root"]).exists()
def test_oracle_malformed_normalizes_to_execution_malformed_and_preserves_workspace(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    fixture = source / "fixture.json"; fixture.write_text('{"state_axes":[]}', encoding="utf-8")
    result = AdapterResult("returned", '{"artifacts":{"one.json":{},"one.md":"bad"}}', [], 1,
                           "14B", "seeded", "", "", {}, {}, [], [], "structured_provider_response")
    manifest = _one_task(source, expected=("one.json", "one.md"),
                         oracle={"checker_id": "shared_task_artifact/v1", "fixture": "fixture.json",
                                 "expected_artifacts": ["one.json", "one.md"]}, inputs=("fixture.json",))
    run = execute_cross_harness_manifest(
        manifest, _runtime(["local_14b"]), {"local_14b": FakeAdapter(result=result)},
        artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="local",
        selectors=["agt-001"], roles=["local_14b"], repetitions=1,
    )
    row = run["rows"][0]
    assert (row["execution_state"], row["oracle_state"], row["primary_outcome"]) == ("malformed", "not_run", "malformed")
    assert row["oracle_evidence"]["reported_state"] == "malformed"
    assert row["oracle_evidence"]["failure_codes"]
    assert Path(row["workspace_root"]).is_dir()
def test_malformed_provider_envelope_preserves_exact_output_bytes(tmp_path):
    source = tmp_path / "source"; source.mkdir(); output = '{"not_artifacts":true}'
    result = AdapterResult("returned", output, [], 1, "14B", "seeded", "", "", {}, {}, [], [], "structured_provider_response")
    run = execute_cross_harness_manifest(_one_task(source, expected=("result.json",)), _runtime(["local_14b"]),
        {"local_14b": FakeAdapter(result=result)}, artifact_root=tmp_path / "artifacts", source_root=source,
        run_id="run", phase="local", selectors=["agt-001"], roles=["local_14b"], repetitions=1)
    row = run["rows"][0]
    assert row["execution_state"] == "malformed"
    assert Path(row["raw_output_path"]).read_bytes() == output.encode()
def test_adapter_value_error_is_internal_not_malformed(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    nonfinite = AdapterResult("returned", "{}", [], 1, "14B", "seeded", "", "", {"memory": float("nan")}, {}, [], [], "structured_provider_response")
    for index, result in enumerate((ValueError("adapter bug"), nonfinite)):
        run = execute_cross_harness_manifest(_one_task(source), _runtime(["local_14b"]),
            {"local_14b": FakeAdapter(result=result)}, artifact_root=tmp_path / f"artifacts-{index}",
            source_root=source, run_id="run", phase="local", selectors=["agt-001"], roles=["local_14b"], repetitions=1)
        assert run["rows"][0]["execution_state"] == "internal_error"
def test_secret_shaped_enforcement_is_rejected_before_artifact_write(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    run = execute_cross_harness_manifest(_one_task(source), _runtime(["local_14b"]),
        {"local_14b": SecretEnforcementAdapter()}, artifact_root=tmp_path / "artifacts", source_root=source,
        run_id="run", phase="local", selectors=["agt-001"], roles=["local_14b"], repetitions=1)
    row = run["rows"][0]
    assert row["execution_state"] == "internal_error"
    assert not (Path(row["attempt_dir"]) / "enforcement.json").exists()
def test_source_mutation_fails_run_and_preserves_attempt_workspace(tmp_path):
    source = tmp_path / "source"; source.mkdir()
    result = AdapterResult("returned", '{"artifacts":{"result.json":{}}}', [], 1, "14B", "seeded", "", "", {}, {}, [], [], "structured_provider_response")
    adapter = FakeAdapter(result=result); original = adapter.execute
    adapter.execute = lambda request: ((source / "mutated.txt").write_text("changed"), original(request))[1]
    with pytest.raises(RuntimeError, match="source_tree_changed"):
        execute_cross_harness_manifest(_one_task(source, expected=("result.json",), oracle={"expected_artifacts": ["result.json"]}),
            _runtime(["local_14b"]), {"local_14b": adapter}, artifact_root=tmp_path / "artifacts", source_root=source,
            run_id="run", phase="local", selectors=["agt-001"], roles=["local_14b"], repetitions=1)
    assert (tmp_path / "artifacts/run/local/local_14b/agt-001-task/rep-001/workspace").is_dir()
def test_receipt_seal_failure_is_explicitly_run_fatal(tmp_path, monkeypatch):
    source = tmp_path / "source"; source.mkdir()
    def fail_seal(*_args): raise OSError("disk failure")
    monkeypatch.setattr("harness.cross_harness_executor._seal_row", fail_seal)
    with pytest.raises(RuntimeError, match="attempt_receipt_seal_failed"):
        execute_cross_harness_manifest(_one_task(source), _runtime(["local_14b"], ready=False),
            {"local_14b": FakeAdapter()}, artifact_root=tmp_path / "artifacts", source_root=source,
            run_id="run", phase="local", selectors=["agt-001"], roles=["local_14b"], repetitions=1)
@pytest.mark.parametrize(("field", "bad"), [
    ("run_id", "../escaped"), ("run_id", "C:escaped"), ("run_id", "C:/escaped"),
    ("run_id", "/absolute"), ("phase", "bad\\path"), ("role", "../role"), ("task_id", "C:/task")])
def test_invalid_identifiers_are_rejected_before_any_directory_creation(tmp_path, monkeypatch, field, bad):
    source = tmp_path / "source"; source.mkdir(); calls = []
    manifest = _one_task(source); options = {"run_id": "run", "phase": "local", "roles": ["local_14b"]}
    if field == "task_id": manifest["task_rows"][0]["task_id"] = bad
    elif field == "role": options["roles"] = [bad]
    else: options[field] = bad
    monkeypatch.setattr(Path, "mkdir", lambda self, *args, **kwargs: calls.append(self))
    with pytest.raises(ValueError):
        execute_cross_harness_manifest(manifest, _runtime(["local_14b"]), {"local_14b": FakeAdapter()},
            artifact_root=tmp_path / "artifacts", source_root=source, selectors=["agt-001"], repetitions=1, **options)
    assert calls == []
