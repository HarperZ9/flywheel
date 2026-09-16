"""shared_task_artifact/v2 binds pre-oracle claims instead of grading prose.

v1 only scans a short literal forbidden-phrase list. The correction leaves v1
alone and adds a diagnostic v2 checker whose JSON claim records and Markdown are
closed projections of facts the oracle can verify before it scores the attempt.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle
from test_cross_harness_oracles import _case, _sha, _sync_output, _write

V1 = "shared_task_artifact/v1"
V2 = "shared_task_artifact/v2"
DIAGNOSTIC_TASK_ID = "agt-003-shared-task-artifact-v2-diagnostic"
ARTIFACTS = ["report.json", "report.md"]
PRE_ORACLE_FACTS = {"execution_state": "returned", "oracle_state": "not_run", "receipt_state": "not_emitted", "pre_oracle_failure_modes": []}
LIMITATION_TEXT = {
    "does_not_prove_provider_superiority": "This attempt does not prove provider superiority.",
    "does_not_prove_cross_harness_comparison": "This attempt does not prove a Codex-vs-Flywheel comparison.",
    "does_not_prove_final_no_failure_completion": "This pre-oracle artifact does not prove final no-failure completion.",
}
PRODUCER_FACTS = {
    "execution_state": "{harness_values.orthogonal_states.execution_state}",
    "oracle_state": "{harness_values.orthogonal_states.oracle_state}",
    "receipt_state": "{harness_values.orthogonal_states.receipt_state}",
    "pre_oracle_failure_modes": "{harness_values.pre_oracle_failure_modes}",
}


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fixture_v2() -> dict:
    return json.loads(Path("benchmarks/fixtures/cross-harness/shared-task-facts-v2.json").read_text(encoding="utf-8"))


def _claim_bindings(facts: dict | None = None) -> list[dict]:
    state_facts = json.loads(json.dumps(PRE_ORACLE_FACTS if facts is None else facts))
    return [
        {"claim_id": "pre_oracle_attempt_state", "claim_type": "pre_oracle_attempt_facts", "subject": "attempt", "authority": "scorecard_core.orthogonal_states", "facts": state_facts},
        {"claim_id": "raw_artifact_binding", "claim_type": "artifact_binding", "subject": "raw_artifact", "authority": "scorecard_core.raw_artifact_sha256", "path_field": "raw_artifact_path", "sha256_field": "raw_artifact_sha256"},
        {"claim_id": "receipt_binding", "claim_type": "artifact_binding", "subject": "receipt", "authority": "scorecard_core.receipt_sha256", "path_field": "receipt_path", "sha256_field": "receipt_sha256"},
        {"claim_id": "provider_superiority_boundary", "claim_type": "limitation", "subject": "attempt", "authority": "shared_task_artifact/v2.closed_limitations", "limitation_id": "does_not_prove_provider_superiority"},
        {"claim_id": "cross_harness_comparison_boundary", "claim_type": "limitation", "subject": "attempt", "authority": "shared_task_artifact/v2.closed_limitations", "limitation_id": "does_not_prove_cross_harness_comparison"},
        {"claim_id": "final_completion_boundary", "claim_type": "limitation", "subject": "attempt", "authority": "shared_task_artifact/v2.closed_limitations", "limitation_id": "does_not_prove_final_no_failure_completion"},
    ]


def _render_markdown(report: dict) -> str:
    facts = next(row["facts"] for row in report["claim_bindings"] if row["claim_id"] == "pre_oracle_attempt_state")
    bindings = {row["claim_id"]: row for row in report["claim_bindings"]}
    limitations = [bindings[key]["limitation_id"] for key in ("provider_superiority_boundary", "cross_harness_comparison_boundary", "final_completion_boundary")]
    lines = [
        f"# {report['task_id']}", "", "## Bound inputs",
        f"- input_sha256s: {_json(report['input_sha256s'])}",
        f"- raw_prompt_sha256: {_json(report['raw_prompt_sha256'])}",
        f"- tool_policy_sha256: {_json(report['tool_policy_sha256'])}", "", "## Bound attempt artifacts",
        f"- raw_artifact_path: {_json(report['raw_artifact_path'])}",
        f"- receipt_path: {_json(report['receipt_path'])}", "", "## Pre-oracle states",
        f"- execution_state: {_json(facts['execution_state'])}",
        f"- oracle_state: {_json(facts['oracle_state'])}",
        f"- receipt_state: {_json(facts['receipt_state'])}",
        f"- pre_oracle_failure_modes: {_json(facts['pre_oracle_failure_modes'])}", "", "## Claim bindings",
        "- pre_oracle_attempt_state: pre_oracle_attempt_facts from scorecard_core.orthogonal_states",
        "- raw_artifact_binding: artifact_binding from raw_artifact_path to scorecard_core.raw_artifact_sha256",
        "- receipt_binding: artifact_binding from receipt_path to scorecard_core.receipt_sha256", "", "## Closed limitations",
    ]
    lines.extend(f"- {item}: {LIMITATION_TEXT[item]}" for item in limitations)
    return "\n".join(lines) + "\n"


def _sync_v2(context: OracleContext, report: dict) -> None:
    _write(context.artifact_paths["report.json"], report)
    context.artifact_paths["report.md"].write_text(_render_markdown(report), encoding="utf-8")
    _sync_output(context, report)


def case_v2(tmp_path: Path) -> tuple[OracleContext, dict, dict]:
    base, _, _ = _case(tmp_path, V1)
    workspace = Path(base.scorecard_core["workspace_root"])
    fixture = _fixture_v2()
    input_hashes = dict(base.expected_input_sha256s)
    _write(workspace / "fixture.json", fixture)
    input_hashes["fixture.json"] = _sha((workspace / "fixture.json").read_bytes())
    core = dict(base.scorecard_core)
    core["orthogonal_states"] = {key: value for key, value in PRE_ORACLE_FACTS.items() if key.endswith("_state")}
    report = {"task_id": DIAGNOSTIC_TASK_ID, "input_sha256s": dict(input_hashes), "raw_prompt_sha256": core["raw_prompt_sha256"], "tool_policy_sha256": core["tool_policy_sha256"], "raw_artifact_path": "raw.txt", "receipt_path": "receipt.json", "pre_oracle_failure_modes": [], "claim_bindings": _claim_bindings()}
    context = OracleContext(DIAGNOSTIC_TASK_ID, {"checker_id": V2, "fixture": "fixture.json", "expected_artifacts": ARTIFACTS}, Path(core["attempt_dir"]) / "output.json", {"report.json": Path(core["attempt_dir"]) / "report.json", "report.md": Path(core["attempt_dir"]) / "report.md"}, input_hashes, core)
    _sync_v2(context, report)
    return context, report, fixture


def test_a_correct_v2_submission_passes_with_verifier_owned_render_hash(tmp_path: Path) -> None:
    context, report, _fixture = case_v2(tmp_path)
    result = evaluate_task_oracle(context)
    assert (result.state, result.failure_codes) == ("pass", [])
    assert result.checker_id == V2
    assert "markdown_render_sha256" not in report
    assert result.evidence["verifier_markdown_render_sha256"] == _sha(_render_markdown(report).encode("utf-8"))


def test_observed_unsupported_paraphrase_passes_v1_and_fails_v2(tmp_path: Path) -> None:
    v1_context, v1_report, _ = _case(tmp_path / "v1", V1)
    v1_context.artifact_paths["report.md"].write_text(f"# {v1_context.task_id}\nBoth harnesses completed with no failures.\n", encoding="utf-8")
    _sync_output(v1_context, v1_report)
    assert evaluate_task_oracle(v1_context).state == "pass"
    v2_context, _, _ = case_v2(tmp_path / "v2")
    v2_context.artifact_paths["report.md"].write_text(_render_markdown(json.loads(v2_context.artifact_paths["report.json"].read_text(encoding="utf-8"))) + "Both harnesses completed with no failures.\n", encoding="utf-8")
    _sync_output(v2_context, json.loads(v2_context.artifact_paths["report.json"].read_text(encoding="utf-8")))
    assert evaluate_task_oracle(v2_context).failure_codes == ["comparison_claim_out_of_scope", "final_status_claim_not_available", "markdown_render_mismatch"]


def test_unknown_json_keys_cannot_smuggle_unchecked_claims(tmp_path: Path) -> None:
    context, report, _ = case_v2(tmp_path); report["extra_fact"] = "unchecked"; _sync_output(context, report)
    assert evaluate_task_oracle(context).failure_codes == ["unsupported_report_field"]


def test_claim_labels_are_rejected_instead_of_read_as_authority(tmp_path: Path) -> None:
    context, report, _ = case_v2(tmp_path); report["claim_bindings"][0]["label"] = "operator summary"; _sync_v2(context, report)
    assert evaluate_task_oracle(context).failure_codes == ["unsupported_claim_field"]


def test_limitation_values_are_rejected_instead_of_freeform_text(tmp_path: Path) -> None:
    context, report, _ = case_v2(tmp_path); report["claim_bindings"][-1]["value"] = "This proves the run had no failures."; _sync_v2(context, report)
    assert evaluate_task_oracle(context).failure_codes == ["unsupported_limitation_value"]


def test_final_pass_assertions_are_not_pre_oracle_facts(tmp_path: Path) -> None:
    context, report, _ = case_v2(tmp_path); report["claim_bindings"][0]["facts"]["oracle_state"] = "pass"; _sync_v2(context, report)
    assert evaluate_task_oracle(context).failure_codes == ["final_status_claim_not_available"]


def test_participant_submitted_markdown_digest_is_an_unsupported_field(tmp_path: Path) -> None:
    context, report, _ = case_v2(tmp_path); report["markdown_render_sha256"] = "0" * 64; _sync_output(context, report)
    assert evaluate_task_oracle(context).failure_codes == ["unsupported_report_field"]


def test_extra_markdown_fails_even_when_json_is_valid(tmp_path: Path) -> None:
    context, report, _ = case_v2(tmp_path)
    context.artifact_paths["report.md"].write_text(_render_markdown(report) + "extra unchecked line\n", encoding="utf-8")
    _sync_output(context, report)
    result = evaluate_task_oracle(context)
    assert result.failure_codes == ["markdown_render_mismatch"]
    assert result.evidence["verifier_markdown_render_sha256"] == _sha(_render_markdown(report).encode("utf-8"))


def test_v2_task_variant_is_bound_without_changing_original_agt003() -> None:
    task_set = json.loads(Path("benchmarks/agentic-task-set-v1.json").read_text(encoding="utf-8"))
    tasks = {row["id"]: row for row in task_set["tasks"]}
    assert tasks["agt-003-codex-flywheel-shared-task"]["oracle"]["checker_id"] == V1
    variant = tasks[DIAGNOSTIC_TASK_ID]
    assert variant["expected_artifacts"] == ["codex_flywheel_shared_task_scorecard.json", "codex_flywheel_shared_task_scorecard.md"]
    assert variant["required_inputs"] == ["benchmarks/fixtures/cross-harness/shared-task-facts-v2.json"]
    assert variant["oracle"] == {"checker_id": V2, "fixture": "benchmarks/fixtures/cross-harness/shared-task-facts-v2.json"}
    fixture = _fixture_v2()
    assert fixture["task_id"] == DIAGNOSTIC_TASK_ID
    assert fixture["failure_code_vocabulary"]["task"] == task_set["oracle_contract"]["checkers"][V2]["failure_codes"]


def test_v2_reference_route_does_not_claim_current_exec_admission() -> None:
    from harness.cross_harness_policy import tool_policy_for

    tasks = {row["id"]: row for row in json.loads(Path("benchmarks/agentic-task-set-v1.json").read_text(encoding="utf-8"))["tasks"]}
    assert tool_policy_for()["allow_exec"] is False
    assert "allowed_workspace_commands" not in tasks[DIAGNOSTIC_TASK_ID]
    assert "Do not submit markdown_render_sha256" in tasks[DIAGNOSTIC_TASK_ID]["prompt"]


def test_registry_carries_v1_and_v2_without_aliasing() -> None:
    from harness.cross_harness_oracles import _CHECKERS

    assert V1 in _CHECKERS and V2 in _CHECKERS
    assert _CHECKERS[V1] is not _CHECKERS[V2]


def test_fixture_exposes_complete_participant_and_verifier_contracts() -> None:
    fixture = _fixture_v2(); contract = fixture["participant_contract"]; verifier = fixture["verifier_contract"]
    assert contract["context_path"] == "benchmark/context.json"
    assert sorted(contract["produces_json_fields"]) == sorted({"task_id", "input_sha256s", "raw_prompt_sha256", "tool_policy_sha256", "raw_artifact_path", "receipt_path", "pre_oracle_failure_modes", "claim_bindings"})
    assert contract["json_serialization"].endswith("ensure_ascii=False)")
    assert contract["claim_bindings"] == _claim_bindings(PRODUCER_FACTS)
    assert contract["markdown_template"][0] == "# {task_id}"
    assert verifier["computes_evidence"] == ["verifier_markdown_render_sha256"]
    assert verifier["hash"]["preimage"] == "canonical Markdown render from participant JSON"


def test_reference_helper_is_not_a_task_input_or_required_for_participant_execution() -> None:
    helper = Path("benchmarks/fixtures/cross-harness/shared-task-v2-producer.py")
    assert helper.is_file()
    assert "harness." not in helper.read_text(encoding="utf-8")
    variant = next(row for row in json.loads(Path("benchmarks/agentic-task-set-v1.json").read_text(encoding="utf-8"))["tasks"] if row["id"] == DIAGNOSTIC_TASK_ID)
    assert helper.as_posix() not in variant["required_inputs"]


def test_executor_synthetic_adapter_scores_v2_without_helper_execution(tmp_path: Path) -> None:
    from harness.cross_harness_adapters import _enforcement
    from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest
    from harness.cross_harness_types import AdapterResult, AvailabilityResult

    class V2Adapter:
        role, adapter_id = "codex_harness", "codex_cli_json/v1"
        output_text = ""; report: dict = {}
        def enforcement(self, _request): return _enforcement({"boundary": "synthetic_read_only", "tool_policy": SHARED_TOOL_POLICY})
        def availability(self, _request): return AvailabilityResult(True, "", "available", {"provider_called": False})
        def execute(self, request):
            assert not (request.workspace_root / "benchmarks/fixtures/cross-harness/shared-task-v2-producer.py").exists()
            context = json.loads((request.workspace_root / "benchmark" / "context.json").read_text(encoding="utf-8"))
            values = context["harness_values"]
            fixture = json.loads((request.workspace_root / "benchmarks/fixtures/cross-harness/shared-task-facts-v2.json").read_text(encoding="utf-8"))
            claims = json.loads(json.dumps(fixture["participant_contract"]["claim_bindings"]))
            states, facts = values["orthogonal_states"], claims[0]["facts"]
            facts["execution_state"] = states["execution_state"]
            facts["oracle_state"] = states["oracle_state"]
            facts["receipt_state"] = states["receipt_state"]
            facts["pre_oracle_failure_modes"] = values["pre_oracle_failure_modes"]
            self.report = {"task_id": values["task_id"], "input_sha256s": values["input_sha256s"], "raw_prompt_sha256": values["raw_prompt_sha256"], "tool_policy_sha256": values["tool_policy_sha256"], "raw_artifact_path": "output.txt", "receipt_path": "provider-receipt.json", "pre_oracle_failure_modes": values["pre_oracle_failure_modes"], "claim_bindings": claims}
            def j(value):
                return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            replacements = {"task_id": self.report["task_id"], "input_sha256s": j(self.report["input_sha256s"]), "raw_prompt_sha256": j(self.report["raw_prompt_sha256"]), "tool_policy_sha256": j(self.report["tool_policy_sha256"]), "raw_artifact_path": j(self.report["raw_artifact_path"]), "receipt_path": j(self.report["receipt_path"]), "execution_state": j(facts["execution_state"]), "oracle_state": j(facts["oracle_state"]), "receipt_state": j(facts["receipt_state"]), "pre_oracle_failure_modes": j(facts["pre_oracle_failure_modes"])}
            markdown = "\n".join(line.format(**replacements) for line in fixture["participant_contract"]["markdown_template"]) + "\n"
            self.output_text = json.dumps({"artifacts": {"codex_flywheel_shared_task_scorecard.json": self.report, "codex_flywheel_shared_task_scorecard.md": markdown}}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            return AdapterResult("returned", self.output_text, [], 5, request.requested_model_reference, "unsupported", "", "", {}, {}, [], [], model_observation_basis="structured_provider_event")

    source = tmp_path / "source"; fixture_rel = Path("benchmarks/fixtures/cross-harness/shared-task-facts-v2.json")
    (source / fixture_rel).parent.mkdir(parents=True); (source / fixture_rel).write_bytes(Path(fixture_rel).read_bytes())
    prompt = "synthetic v2 participant envelope"
    expected_artifacts = ["codex_flywheel_shared_task_scorecard.json", "codex_flywheel_shared_task_scorecard.md"]
    task = {"task_id": DIAGNOSTIC_TASK_ID, "raw_prompt": prompt, "raw_prompt_sha256": _sha(prompt.encode()), "input_sha256s": {fixture_rel.as_posix(): _sha((source / fixture_rel).read_bytes())}, "required_inputs": [fixture_rel.as_posix()], "expected_artifacts": expected_artifacts, "oracle": {"checker_id": V2, "fixture": fixture_rel.as_posix(), "expected_artifacts": expected_artifacts}, "benchmark_id": "cross_harness_reproducibility_matrix", "coverage_unit": DIAGNOSTIC_TASK_ID}
    manifest = {"task_set_id": "flywheel_agentic_gauntlet_v1", "task_rows": [task], "provider_specs": [{"provider_role": "codex_harness", "harness_id": "codex", "adapter_id": "codex_cli_json/v1", "model_id": "synthetic", "model_display_name": "Synthetic", "requested_model_reference": "synthetic"}]}
    adapter = V2Adapter()
    row = execute_cross_harness_manifest(manifest, {"runtime_rows": [{"provider_role": "codex_harness", "focused_run_ready": True, "blocking_gates": []}]}, {"codex_harness": adapter}, artifact_root=tmp_path / "artifacts", source_root=source, run_id="v2", phase="synthetic", selectors=[DIAGNOSTIC_TASK_ID], roles=["codex_harness"], repetitions=1, source_commit="test")["rows"][0]
    assert (row["primary_outcome"], row["oracle_state"], row["receipt_state"]) == ("completed", "pass", "verified")
    assert "markdown_render_sha256" not in adapter.report
    assert Path(row["raw_output_path"]).read_text(encoding="utf-8") == adapter.output_text
    assert json.loads(Path(row["tool_trace_path"]).read_text(encoding="utf-8")) == []
    assert row["oracle_evidence"]["evidence"]["verifier_markdown_render_sha256"] == _sha(_render_markdown(adapter.report).encode("utf-8"))


@pytest.mark.parametrize("axis", ["execution_state", "oracle_state", "receipt_state"])
@pytest.mark.parametrize("bad", [[], {}, None, True, 1])
def test_pre_oracle_state_values_must_be_strings_not_adversarial_json_types(tmp_path: Path, axis: str, bad) -> None:
    context, report, _ = case_v2(tmp_path)
    report["claim_bindings"][0]["facts"][axis] = bad
    _sync_v2(context, report)
    result = evaluate_task_oracle(context)
    assert (result.state, result.failure_codes) == ("malformed", ["json_invalid"])
    assert result.evidence["reason"] == "pre_oracle_facts_type_invalid"
