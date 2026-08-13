import hashlib, json, os, shutil
from pathlib import Path

import pytest

import harness.cross_harness_artifacts as artifact_module

from harness.cross_harness_artifacts import (
    bind_attempt_receipt,
    canonical_sha256,
    create_attempt_workspace,
    materialize_response_envelope,
    preflight_artifact_root,
    recheck_attempt_receipt,
    snapshot_source_tree,
    write_artifact_index,
)
from harness.cross_harness_executor import comparison_key, execute_cross_harness_manifest
from harness.cross_harness_types import AdapterResult, AvailabilityResult, EnforcementResult


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_external_root_preflight_rejects_inside_case_and_resolved_symlink(tmp_path):
    source = tmp_path / "Source"
    source.mkdir()
    with pytest.raises(ValueError, match="artifact_root_inside_source"):
        preflight_artifact_root(source, source / "new" / "artifacts")
    if os.name == "nt":
        with pytest.raises(ValueError, match="artifact_root_inside_source"):
            preflight_artifact_root(Path(str(source).swapcase()), source / "more")
    link = tmp_path / "linked"
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable")
    with pytest.raises(ValueError, match="artifact_root_inside_source"):
        preflight_artifact_root(source, link / "nested")


def test_preflight_uses_nearest_existing_parent_without_creating_root(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    proposed = tmp_path / "outside" / "new" / "run"
    assert preflight_artifact_root(source, proposed) == proposed.resolve()
    assert not (tmp_path / "outside").exists()


def test_preflight_rejects_resolved_alias_and_lexical_child_with_deterministic_seam(tmp_path, monkeypatch):
    source, outside = tmp_path / "source", tmp_path / "outside"
    source.mkdir(); outside.mkdir()
    monkeypatch.setattr(artifact_module, "_resolve_from_existing_parent", lambda _path: source.resolve())
    with pytest.raises(ValueError, match="artifact_root_inside_source"):
        preflight_artifact_root(source, outside / "alias")
    monkeypatch.setattr(artifact_module, "_resolve_from_existing_parent", lambda _path: outside.resolve())
    with pytest.raises(ValueError, match="artifact_root_inside_source"):
        preflight_artifact_root(source, source / "lexical-child")

def test_workspace_inputs_are_independent_read_only_copies_and_snapshot_is_stable(tmp_path):
    source, attempt = tmp_path / "source", tmp_path / "run" / "attempt"
    original = source / "fixtures" / "facts.json"
    original.parent.mkdir(parents=True)
    original.write_text('{"fact":1}', encoding="utf-8")
    before = snapshot_source_tree(source)
    workspace, hashes = create_attempt_workspace(
        source, ["fixtures/facts.json"], {"fixtures/facts.json": _sha(original)}, attempt
    )
    copied = workspace / "fixtures" / "facts.json"
    assert copied.read_bytes() == original.read_bytes()
    assert os.stat(copied).st_ino != os.stat(original).st_ino
    assert copied.stat().st_nlink == 1
    assert copied.stat().st_mode & 0o222 == 0
    assert hashes == {"fixtures/facts.json": _sha(original)}
    assert snapshot_source_tree(source) == before

def test_snapshot_separates_copy_comparison_from_workspace_identity(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir(); right.mkdir()
    for root in (left, right): root.joinpath("same.txt").write_text("same", encoding="utf-8")
    first, independent = snapshot_source_tree(left), snapshot_source_tree(right)
    assert first["sha256"] == independent["sha256"]
    assert first["identity_sha256"] != independent["identity_sha256"]
    base = {"task_set_id": "set", "task_id": "task", "raw_prompt_sha256": "a" * 64,
            "tool_policy_sha256": "b" * 64, "model_id": "model", "cache_state": "cold",
            "phase": "local", "execution_mode": "focused_run", "source_snapshot_sha256": "c" * 64,
            "input_sha256s": {}}
    assert comparison_key({**base, "workspace_snapshot_sha256": first["sha256"]}) == comparison_key(
        {**base, "workspace_snapshot_sha256": independent["sha256"]})
    left.joinpath("same.txt").unlink(); left.joinpath("same.txt").write_text("same", encoding="utf-8")
    replaced = snapshot_source_tree(left)
    assert replaced["sha256"] == first["sha256"] and replaced != first

@pytest.mark.parametrize("names", [
    ["/absolute.json"], ["../escape.json"], ["a/nested.json"], ["a\\nested.json"],
    ["same.json", "same.json"], ["Same.json", "same.json"], ["report.json:stream"],
    ["CON.json"], ["trailing.json."], ["output.txt"],
])
def test_declared_artifact_names_reject_absolute_traversal_and_duplicates(tmp_path, names):
    with pytest.raises(ValueError, match="declared artifact"):
        materialize_response_envelope('{"artifacts":{}}', names, tmp_path)

@pytest.mark.parametrize("payload", [
    '{"artifacts":{"one.json":{},"extra.md":"x"}}',
    '{"artifacts":{}}',
    '{"artifacts":{"one.json":{},"one.json":{}}}',
    '{"artifacts":{"../one.json":{}}}',
])
def test_materialization_rejects_undeclared_missing_duplicate_and_traversal_names(tmp_path, payload):
    with pytest.raises(ValueError, match="artifact"):
        materialize_response_envelope(payload, ["one.json"], tmp_path)

def test_materialization_writes_only_exact_declared_artifacts(tmp_path):
    raw, paths = materialize_response_envelope(
        '{"artifacts":{"report.json":{"value":1},"report.md":"# Result\\n"}}',
        ["report.json", "report.md"], tmp_path,
    )
    assert raw == tmp_path / "output.txt"
    assert json.loads(paths["report.json"].read_text(encoding="utf-8")) == {"value": 1}
    assert paths["report.md"].read_text(encoding="utf-8") == "# Result\n"
    assert {path.name for path in tmp_path.iterdir()} == {"output.txt", "report.json", "report.md"}

def test_receipt_binds_canonical_row_and_recheck_detects_row_or_artifact_tamper(tmp_path):
    artifact = tmp_path / "report.json"
    artifact.write_text('{"value":1}\n', encoding="utf-8")
    row = {"schema": "harness.cross-harness-task-scorecard/v1", "attempt_key": ["run", "phase", "role", "task", 1],
           "task_id": "agt-001", "execution_state": "returned", "raw_prompt_sha256": "a" * 64,
           "raw_output_sha256": _sha(artifact), "enforcement_sha256": "b" * 64,
           "tool_policy_sha256": "c" * 64, "workspace_snapshot_sha256": "d" * 64,
           "input_sha256s": {"fixture": "e" * 64}, "comparison_key": "f" * 64,
           "model_observed": "model-a", "availability_evidence": {"blocking_gates": []},
           "oracle_state": "pass", "oracle_evidence": {"failure_codes": []}, "receipt_state": "verified",
           "orthogonal_states": {"execution_state": "returned", "oracle_state": "pass", "receipt_state": "verified"},
           "primary_outcome": "completed", "status": "executed", "failure_class": "", "failure_detail": "",
           "metrics": {"latency_ms": 4}, "metric_null_reasons": {}}
    receipt_path = tmp_path / "receipt.json"
    receipt = bind_attempt_receipt(row, {"report.json": artifact}, receipt_path)
    assert receipt["receipt_subject_sha256"]
    assert recheck_attempt_receipt(receipt_path, row) == "verified"
    assert recheck_attempt_receipt(receipt_path, {**row, "task_id": "changed"}) == "drift"
    assert recheck_attempt_receipt(receipt_path, {**row, "oracle_state": "fail",
                                                  "primary_outcome": "oracle_fail"}) == "drift"
    for field, value in (("input_sha256s", {}), ("comparison_key", "0" * 64),
                         ("model_observed", "model-b"), ("availability_evidence", {"blocking_gates": ["stale"]})):
        assert recheck_attempt_receipt(receipt_path, {**row, field: value}) == "drift"
    for field, value in (("metrics", {}), ("failure_detail", "changed"), ("status", "invalid"),
                         ("receipt_state", "drift"), ("metric_null_reasons", {"usage": "missing"})):
        assert recheck_attempt_receipt(receipt_path, {**row, field: value}) == "drift"
    assert receipt["does_not_bind"] == ["receipt_does_not_bind", "receipt_sha256", "receipt_subject_sha256"]
    artifact.write_text('{"value":2}\n', encoding="utf-8")
    assert recheck_attempt_receipt(receipt_path, row) == "drift"

def test_canonical_serializer_rejects_nonfinite_numbers():
    with pytest.raises(ValueError):
        canonical_sha256({"latency": float("nan")})

def test_artifact_index_hashes_references_but_explicitly_excludes_itself(tmp_path):
    one, two = tmp_path / "one.txt", tmp_path / "nested" / "two.txt"
    one.write_text("one", encoding="utf-8")
    two.parent.mkdir()
    two.write_text("two", encoding="utf-8")
    path = write_artifact_index(tmp_path, [one, two, one])
    index = json.loads(path.read_text(encoding="utf-8"))
    assert [row["path"] for row in index["artifacts"]] == ["nested/two.txt", "one.txt"]
    assert index["self_hash"] is None
    assert index["self_hash_reason"] == "artifact index cannot contain its own hash"

class _ExecAdapter:
    role, adapter_id = "local_14b", "local/v1"
    def __init__(self, result, mutate=""): self.result, self.mutate, self.calls = result, mutate, []
    def enforcement(self, request):
        value = {"boundary": "read-only"}; return EnforcementResult(value, canonical_sha256(value), "adapter_claim", "non_equivalent")
    def availability(self, request): return AvailabilityResult(True, "", "ready", {})
    def execute(self, request):
        self.calls.append(request.task_id)
        target = request.workspace_root / "input.txt"
        if self.mutate == "create": request.workspace_root.chmod(0o700); (request.workspace_root / "created.txt").write_text("new")
        if self.mutate == "replace": target.chmod(0o600); target.write_text("replaced")
        if self.mutate == "relink":
            request.workspace_root.chmod(0o700); target.chmod(0o600); target.unlink(); os.link(request.artifact_dir / "prompt.txt", target)
        if self.mutate == "mode": target.chmod(0o600)
        if self.mutate == "delete_first" and request.task_id == "agt-001-task":
            request.workspace_root.chmod(0o700); target.chmod(0o600); shutil.rmtree(request.workspace_root)
        if isinstance(self.result, Exception): raise self.result
        return self.result(request) if callable(self.result) else self.result

def _execute_fixture(tmp_path, adapter, task_ids=("agt-001-task",), expected=("result.json",), oracle=None, input_text="original"):
    source = tmp_path / "source"; source.mkdir(); source.joinpath("input.txt").write_text(input_text)
    digest = _sha(source / "input.txt")
    tasks = [{"task_id": task_id, "raw_prompt": "prompt\n", "raw_prompt_sha256": hashlib.sha256(b"prompt\n").hexdigest(),
              "required_inputs": ["input.txt"], "input_sha256s": {"input.txt": digest},
              "expected_artifacts": list(expected), "oracle": oracle or {"expected_artifacts": list(expected)}}
             for task_id in task_ids]
    manifest = {"task_set_id": "set", "task_rows": tasks, "provider_specs": [
        {"provider_role": "local_14b", "harness_id": "local", "adapter_id": "local/v1", "model_id": "flywheel-local-coder-14b", "model_display_name": "Local 14B", "requested_model_reference": "local:14b"}]}
    runtime = {"runtime_rows": [{"provider_role": "local_14b", "focused_run_ready": True,
                "blocking_gates": [], "endpoint_profile_matches": [], "endpoint_gate_matches": []}]}
    root = tmp_path / "artifacts"
    run = execute_cross_harness_manifest(manifest, runtime, {"local_14b": adapter}, artifact_root=root,
        source_root=source, run_id="run", phase="local", selectors=list(task_ids), roles=["local_14b"], repetitions=1)
    return run, root

@pytest.mark.parametrize("mutation", ["create", "replace", "relink", "mode"])
def test_workspace_mutation_is_typed_drift_preserved_and_indexed(tmp_path, mutation):
    result = AdapterResult("returned", '{"artifacts":{"result.json":{}}}', [], 1, "14B", "seeded", "", "", {}, {}, [], [], "structured_provider_response")
    run, root = _execute_fixture(tmp_path, _ExecAdapter(result, mutation))
    row = run["rows"][0]
    assert (row["execution_state"], row["failure_class"], row["workspace_state"]) == ("malformed", "workspace_drift", "drift")
    assert Path(row["workspace_root"]).is_dir()
    after = json.loads((Path(row["attempt_dir"]) / "workspace-after.json").read_text())
    assert {item["path"] for item in after["files"]} >= ({"created.txt"} if mutation == "create" else {"input.txt"})
    index = json.loads((root / "run" / "artifact-index.json").read_text())
    assert any(item["path"].endswith("workspace-after.json") for item in index["artifacts"])

def test_missing_workspace_is_typed_indexed_and_does_not_abort_later_tasks(tmp_path):
    result = AdapterResult("returned", '{"artifacts":{"result.json":{}}}', [], 1, "14B", "seeded", "", "", {}, {}, [], [], "structured_provider_response")
    adapter = _ExecAdapter(result, "delete_first")
    run, root = _execute_fixture(tmp_path, adapter, ("agt-001-task", "agt-002-task"))
    assert adapter.calls == ["agt-001-task", "agt-002-task"]
    assert (run["rows"][0]["execution_state"], run["rows"][0]["failure_class"]) == ("malformed", "workspace_drift")
    after = json.loads((Path(run["rows"][0]["attempt_dir"]) / "workspace-after.json").read_text())
    assert after["state"] == "snapshot_error"
    assert (root / "run" / "run.json").is_file()
    index = json.loads((root / "run" / "artifact-index.json").read_text())
    assert sum(item["path"].endswith("workspace-after.json") for item in index["artifacts"]) == 2

class _SecretAdapter(_ExecAdapter):
    def availability(self, request):
        return AvailabilityResult(True, "", "Authorization: Bearer TOP-SECRET", {"note": "token=TOP-SECRET"})


def test_secret_values_are_redacted_from_every_serialized_surface(tmp_path):
    result = AdapterResult("malformed", "terminal bytes", [{"note": "Authorization: Bearer TOP-SECRET"}], 1,
        "token=TOP-SECRET", "secret=TOP-SECRET", "failure", "password=TOP-SECRET",
        {"note": "api_key=TOP-SECRET"}, {"note": "token=TOP-SECRET"},
        ["Authorization: Bearer TOP-SECRET"], ["secret=TOP-SECRET"], "structured_provider_response")
    run, root = _execute_fixture(tmp_path, _SecretAdapter(result))
    assert run["rows"][0]["execution_state"] == "malformed"
    assert "TOP-SECRET" not in "\n".join(path.read_text(errors="ignore") for path in root.rglob("*") if path.is_file())


@pytest.mark.parametrize("state", ["malformed", "timeout", "internal_error", "unavailable"])
def test_nonreturn_terminal_output_is_preserved_with_denominator_fields(tmp_path, state):
    output = f"exact terminal bytes {state}"
    result = AdapterResult(state, output, [], 4, "14B", "unsupported", state, "detail", {}, {}, [], [], "structured_provider_response")
    run, _ = _execute_fixture(tmp_path, _ExecAdapter(result)); row = run["rows"][0]
    assert Path(row["raw_output_path"]).read_bytes() == output.encode()
    assert (row["planned"], row["admitted"], row["launched"], row["blocked"]) == (True, True, True, state == "unavailable")
    assert row["metric_null_reasons"]["cost"] and row["metric_null_reasons"]["usage"]


def test_live_timeout_is_typed_and_sealed(tmp_path):
    run, _ = _execute_fixture(tmp_path, _ExecAdapter(TimeoutError("deadline"))); row = run["rows"][0]
    assert (row["execution_state"], row["status"], row["launched"]) == ("timeout", "failed", True)
    assert row["receipt_state"] == "verified" and row["metric_null_reasons"]["latency"]


@pytest.mark.parametrize("elapsed", [float("nan"), -1, True])
def test_invalid_elapsed_is_isolated_internal_error(tmp_path, elapsed):
    result = AdapterResult("returned", '{"artifacts":{"result.json":{}}}', [], elapsed, "14B", "seeded", "", "", {}, {}, [], [], "structured_provider_response")
    run, _ = _execute_fixture(tmp_path, _ExecAdapter(result)); row = run["rows"][0]
    assert row["execution_state"] == "internal_error" and row["receipt_state"] == "verified"


def test_multirow_adapter_exception_is_isolated(tmp_path):
    def result(request):
        if request.task_id == "agt-001-task": raise ValueError("first row bug")
        return AdapterResult("returned", '{"artifacts":{"result.json":{}}}', [], 1, "14B", "seeded", "", "", {}, {}, [], [], "structured_provider_response")
    run, _ = _execute_fixture(tmp_path, _ExecAdapter(result), ("agt-001-task", "agt-002-task"))
    assert [row["execution_state"] for row in run["rows"]] == ["internal_error", "returned"]


def test_snapshot_streams_regular_files_and_detects_concurrent_mutation(tmp_path, monkeypatch):
    path = tmp_path / "large.bin"; path.write_bytes(b"initial")
    monkeypatch.setattr(Path, "read_bytes", lambda _self: (_ for _ in ()).throw(AssertionError("read_bytes forbidden")))
    original = artifact_module._sha_file
    def mutate(candidate):
        digest = original(candidate); candidate.write_bytes(b"changed-size"); return digest
    monkeypatch.setattr(artifact_module, "_sha_file", mutate)
    with pytest.raises(ValueError, match="concurrent mutation"):
        snapshot_source_tree(tmp_path)


def test_live_oracle_fail_and_final_row_receipt_tamper(tmp_path):
    fixture = json.dumps({"events": []})
    def result(request):
        report = {"task_id": request.task_id, "input_sha256s": request.input_sha256s,
                  "failure_classes": ["wrong"], "cited_event_ids": [], "receipt_input_sha256s": request.input_sha256s}
        output = json.dumps({"artifacts": {"result.json": report, "result.md": f"# {request.task_id}\n"}})
        return AdapterResult("returned", output, [], 1, "14B", "seeded", "", "", {}, {}, [], [], "structured_provider_response")
    oracle = {"checker_id": "index_fallback_integrity/v1", "fixture": "input.txt",
              "expected_artifacts": ["result.json", "result.md"]}
    run, _ = _execute_fixture(tmp_path, _ExecAdapter(result), ("agt-001-index-fallback-integrity",),
                              ("result.json", "result.md"), oracle, fixture)
    row = run["rows"][0]; receipt = Path(row["receipt_path"])
    assert (row["oracle_state"], row["primary_outcome"], row["receipt_state"]) == ("fail", "oracle_fail", "verified")
    assert recheck_attempt_receipt(receipt, {**row, "metrics": {}}) == "drift"
    receipt.write_text(receipt.read_text().replace("receipt_subject_sha256", "tampered_subject_sha256"))
    assert recheck_attempt_receipt(receipt, row) == "drift"
