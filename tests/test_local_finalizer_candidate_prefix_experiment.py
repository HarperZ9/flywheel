import base64
import json
import hashlib
from types import SimpleNamespace

import pytest

from harness.local_finalizer_experiment import (
    FIXED_PARAMS,
    LocalCandidatePrefixRunner,
    arm_request_shapes,
    build_nonleaky_overlay,
    run_candidate_prefix_experiment,
    schema_for_task,
)
from harness.local_agent import OllamaBackend
from scripts.run_local_finalizer_candidate_prefix_experiment import build_tasks


def _task(task_id="agt-017-budgeted-evidence-selection"):
    return {"task_id": task_id, "expected_artifacts": ["report.json", "report.md"],
            "oracle": {"checker_id": "budgeted_evidence_selection/v1", "fixture": "oracle.json",
                       "expected_artifacts": ["report.json", "report.md"],
                       "required_json_fields": ["task_id", "input_sha256s", "selected",
                                                "total_cost_usd", "total_value"],
                       "json_field_contract": {
                           "task_id": "string, exactly the canonical task id",
                           "input_sha256s": "object mapping each required input path to its 64-character lowercase hex sha256",
                           "selected": "array of strings, distinct item_id values from the fixture pool",
                           "total_cost_usd": "number, the summed cost_usd of the selected items, exact to whole cents",
                           "total_value": "number, the summed evidence_value of the selected items"}},
            "visible_input_sha256s": {"visible.json": "a" * 64},
            "oracle_input_sha256s": {"oracle.json": "b" * 64},
            "prompt": "prompt", "raw_prompt_sha256": "c" * 64}


def _candidate(task, params, out_dir):
    return {"state": "returned", "eligible": True, "candidate_state": "eligible_no_test_no_criteria",
            "selected_text": json.dumps({"artifacts": {"report.json": {"task_id": task["task_id"],
            "input_sha256s": task["visible_input_sha256s"], "selected": [], "total_cost_usd": 0,
            "total_value": 0}, "report.md": f"# {task['task_id']}\n"}}),
            "context": {"history": [{"role": "assistant", "content": "candidate"}],
                        "candidate_text": "candidate", "candidate_state": "eligible_no_test_no_criteria",
                        "candidate_sha256": "d" * 64, "pre_finalizer_checkpoint": "p" * 64},
            "normal_call_count": 1, "elapsed_ms": 11, "tool_trace": []}


def test_arm_request_shapes_differ_only_by_native_format():
    task = _task()
    a, b = arm_request_shapes(task, {"history": [{"role": "assistant", "content": "candidate"}]}, FIXED_PARAMS)

    b_without_format = dict(b)
    assert b_without_format.pop("format") == a["schema"]
    assert b_without_format == {k: v for k, v in a.items() if k != "schema"}


def test_b_schema_contains_visible_required_json_field_contract():
    report = schema_for_task(_task())["properties"]["artifacts"]["properties"]["report.json"]

    assert report["required"] == ["task_id", "input_sha256s", "selected", "total_cost_usd", "total_value"]
    assert report["properties"]["task_id"] == {"type": "string"}
    assert report["properties"]["input_sha256s"]["additionalProperties"] == {"type": "string"}
    assert report["properties"]["selected"] == {"type": "array", "items": {"type": "string"}}
    assert report["properties"]["total_cost_usd"] == {"type": "number"}


def test_runner_scores_c_without_call_and_preserves_failed_finalizer_denominator(tmp_path):
    calls = []

    def finalizer(arm, task, candidate, params, out_dir):
        calls.append(arm)
        if arm == "A":
            return {"state": "request_rejected", "selected_text": "", "request_body_sha256": "e" * 64}
        return {"state": "returned", "selected_text": candidate["selected_text"], "request_body_sha256": "f" * 64}

    summary = run_candidate_prefix_experiment([_task()], tmp_path / "run", FIXED_PARAMS,
                                              candidate_runner=_candidate,
                                              finalizer_runner=finalizer,
                                              score_runner=lambda task, arm, text, attempt, candidate: ("pass", []))

    rows = summary["rows"]
    assert [row["arm"] for row in rows] == ["C", "A", "B"]
    assert rows[0]["model_calls_after_prefix"] == 0
    assert rows[0]["oracle_state"] == "pass"
    assert rows[1]["finalizer_state"] == "request_rejected"
    assert rows[1]["oracle_state"] == "not_run"
    assert rows[2]["oracle_state"] == "pass"
    assert calls == ["A", "B"]
    assert (tmp_path / "run" / "pre-run-manifest.json").is_file()
    assert (tmp_path / "run" / "run-summary.json").is_file()


def test_systemic_finalizer_failure_stops_arm_without_losing_rows(tmp_path):
    calls = []

    def finalizer(arm, task, candidate, params, out_dir):
        calls.append((task["task_id"], arm))
        if arm == "A":
            return {"state": "request_rejected", "selected_text": "", "request_body_sha256": "e" * 64}
        return {"state": "returned", "selected_text": candidate["selected_text"], "request_body_sha256": "f" * 64}

    tasks = [_task("agt-017-budgeted-evidence-selection"), _task("agt-018-budgeted-evidence-selection")]
    summary = run_candidate_prefix_experiment(tasks, tmp_path / "run", FIXED_PARAMS,
                                              candidate_runner=_candidate,
                                              finalizer_runner=finalizer,
                                              score_runner=lambda task, arm, text, attempt, candidate: ("pass", []))

    rows = summary["rows"]
    assert len(rows) == 6
    assert [call[1] for call in calls] == ["A", "B", "B"]
    assert rows[4]["arm"] == "A"
    assert rows[4]["finalizer_state"] == "not_started_after_systemic_finalizer_block"
    assert rows[4]["oracle_state"] == "not_run"
    assert rows[4]["model_calls_after_prefix"] == 0


def test_ineligible_candidate_rows_carry_typed_reason(tmp_path):
    def ineligible(task, params, out_dir):
        return {"state": "returned", "eligible": False,
                "candidate_state": "max_steps_reached",
                "selected_text": "[max_steps reached without a final answer]",
                "workspace_root": tmp_path, "tool_policy": {}}

    summary = run_candidate_prefix_experiment([_task()], tmp_path / "run", FIXED_PARAMS,
                                              candidate_runner=ineligible,
                                              finalizer_runner=lambda *a: (_ for _ in ()).throw(AssertionError("no call")),
                                              score_runner=lambda *a: ("not_run", []))

    assert [row["finalizer_state"] for row in summary["rows"]] == [
        "max_steps_not_eligible", "max_steps_not_eligible", "max_steps_not_eligible"]
    assert [row["oracle_state"] for row in summary["rows"]] == ["not_run", "not_run", "not_run"]
    assert summary["rows"][1]["failure_codes"] == ["max_steps_not_eligible"]


def test_nonleaky_overlay_removes_visible_oracle_labels(tmp_path):
    source = tmp_path / "source"
    fixture_dir = source / "benchmarks" / "fixtures" / "cross-harness"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "evidence-bound-claims-v1.json").write_text(json.dumps({
        "measurements": [{"measurement_id": "m1", "value": 1, "denominator": 2, "interval_95": [0, 1]}],
        "claims": [{"claim_id": "c1", "text": "x", "supported_by": ["m1"]}]}), encoding="utf-8")
    (fixture_dir / "source-contradiction-records-v1.json").write_text(json.dumps({
        "records": [{"record_id": "r1", "field": "a", "value": "1"}],
        "contradiction_pairs": [["r1", "r2"]], "reconcilable_pairs": []}), encoding="utf-8")

    overlay = build_nonleaky_overlay(source, tmp_path / "overlay")

    visible_paths = [tmp_path / "overlay" / row["visible_fixture"] for row in overlay]
    visible_text = "\n".join(path.read_text(encoding="utf-8") for path in visible_paths)
    assert "supported_by" not in visible_text
    assert "contradiction_pairs" not in visible_text
    assert "reconcilable_pairs" not in visible_text
    assert all(len(row["visible_input_sha256s"].values()) == 1 for row in overlay)
    assert all(len(next(iter(row["oracle_input_sha256s"].values()))) == 64 for row in overlay)


def test_workspace_refuses_visible_input_hash_drift(tmp_path):
    source = tmp_path / "visible.json"
    source.write_text("{}", encoding="utf-8")
    task = {**_task(), "visible_sources": {"visible.json": source},
            "visible_input_sha256s": {"visible.json": "0" * 64}}

    runner = LocalCandidatePrefixRunner(SimpleNamespace(), tmp_path, FIXED_PARAMS)

    with pytest.raises(ValueError, match="visible input hash mismatch"):
        runner._workspace(task, tmp_path / "attempt")


def test_candidate_checks_adapter_availability_before_backend(tmp_path):
    source = tmp_path / "visible.json"
    source.write_text("{}", encoding="utf-8")
    visible_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    task = {**_task(), "visible_sources": {"visible.json": source},
            "visible_input_sha256s": {"visible.json": visible_hash}}

    class Adapter:
        role = "local_14b"
        adapter_id = "local-http"
        profile = {"model_ref": "local-model"}

        def availability(self, req):
            return SimpleNamespace(available=False, failure_class="unsupported")

        def backend_factory(self, profile, timeout):
            raise AssertionError("backend should not be constructed")

    with pytest.raises(RuntimeError, match="unsupported"):
        LocalCandidatePrefixRunner(Adapter(), tmp_path, FIXED_PARAMS).candidate(task, FIXED_PARAMS, tmp_path / "attempt")


def test_script_builds_prompts_for_overlay_inputs(tmp_path):
    source = tmp_path / "source"
    fixture_dir = source / "benchmarks" / "fixtures" / "cross-harness"
    fixture_dir.mkdir(parents=True)
    for name in ("evidence-bound-claims-v1.json", "source-contradiction-records-v1.json",
                 "budgeted-evidence-pool-v1.json"):
        (fixture_dir / name).write_text("{}", encoding="utf-8")
    task_set = {"task_set_id": "canonical", "oracle_contract": {"checkers": {
        "evidence_bound_reporting/v1": {"required_json_fields": ["task_id"], "json_field_contract": {"task_id": "string"}},
        "contradiction_detection/v1": {"required_json_fields": ["task_id"], "json_field_contract": {"task_id": "string"}},
        "budgeted_evidence_selection/v1": {"required_json_fields": ["task_id"], "json_field_contract": {"task_id": "string"}},
    }}, "tasks": [
        {"id": "agt-015-evidence-bound-reporting", "lane": "lane", "difficulty": "focused",
         "prompt": "base 15", "required_inputs": ["benchmarks/fixtures/cross-harness/evidence-bound-claims-v1.json"],
         "expected_artifacts": ["report.json", "report.md"], "scoring_focus": [], "must_not": [],
         "oracle": {"checker_id": "evidence_bound_reporting/v1", "fixture": "unused"}},
        {"id": "agt-016-source-contradiction-detection", "lane": "lane", "difficulty": "focused",
         "prompt": "base 16", "required_inputs": ["benchmarks/fixtures/cross-harness/source-contradiction-records-v1.json"],
         "expected_artifacts": ["report.json", "report.md"], "scoring_focus": [], "must_not": [],
         "oracle": {"checker_id": "contradiction_detection/v1", "fixture": "unused"}},
        {"id": "agt-017-budgeted-evidence-selection", "lane": "lane", "difficulty": "focused",
         "prompt": "base 17", "required_inputs": ["benchmarks/fixtures/cross-harness/budgeted-evidence-pool-v1.json"],
         "expected_artifacts": ["report.json", "report.md"], "scoring_focus": [], "must_not": [],
         "oracle": {"checker_id": "budgeted_evidence_selection/v1", "fixture": "benchmarks/fixtures/cross-harness/budgeted-evidence-pool-v1.json"}},
    ]}
    task_set_path, contract_path = tmp_path / "tasks.json", tmp_path / "contract.json"
    task_set_path.write_text(json.dumps(task_set), encoding="utf-8")
    contract_path.write_text(json.dumps({"contract_id": "contract", "global_invariants": []}), encoding="utf-8")

    tasks = build_tasks(source, task_set_path, contract_path, tmp_path / "run")

    assert "Task set: local_finalizer_heldout_revised_20260908" in tasks[0]["prompt"]
    assert "Task id: lfh-015-evidence-bound-nonleaky" in tasks[0]["prompt"]
    assert "- visible/lfh-015-evidence-bound-nonleaky.json" in tasks[0]["prompt"]
    assert "benchmarks/fixtures/cross-harness/evidence-bound-claims-v1.json" not in tasks[0]["prompt"]


def test_local_finalizer_runner_uses_real_factory_and_ab_requests_differ_only_by_format(tmp_path):
    bodies = []
    class Adapter:
        role = "local_14b"
        adapter_id = "openai_compatible_local/v1"
        profile = {"profile_id": "local-14b", "backend": "ollama", "model_ref": "ollama:qwen2.5:7b",
                   "endpoint_url": "http://127.0.0.1:11434",
                   "structured_final_output": {"state": "verified",
                                               "transport": "ollama_chat_format_json_schema"}}

        def backend_factory(self, profile, timeout):
            def transport(method, url, body, timeout):
                decoded = json.loads(body.decode("utf-8"))
                bodies.append(decoded)
                return 200, {"message": {"content": "final"}, "model": decoded["model"],
                             "done": True, "done_reason": "stop"}
            return OllamaBackend(base_url=profile["endpoint_url"], model=profile["model_ref"],
                                 timeout=timeout, transport=transport)

    candidate = {"workspace_root": tmp_path, "context": {"candidate_text": "candidate"},
                 "normal_call_count": 1}
    runner = LocalCandidatePrefixRunner(Adapter(), tmp_path, FIXED_PARAMS)
    out_a = runner.finalizer("A", _task(), candidate, FIXED_PARAMS, tmp_path / "attempt-a")
    out_b = runner.finalizer("B", _task(), candidate, FIXED_PARAMS, tmp_path / "attempt-b")

    body_a, body_b_original = bodies[0], json.loads(json.dumps(bodies[1]))
    body_b = json.loads(json.dumps(body_b_original))
    assert "format" not in body_a
    assert body_b.pop("format") == schema_for_task(_task())
    assert body_a == body_b
    persisted_b = json.loads((tmp_path / "attempt-b" / "structured-finalizer-result.json").read_text(encoding="utf-8"))
    persisted_body = json.loads(base64.b64decode(persisted_b["evidence"]["request_body_b64"]).decode("utf-8"))
    assert persisted_body == body_b_original
    assert out_a["state"] == out_b["state"] == "returned"
