import json
from pathlib import Path

import pytest

from harness.cross_harness_oracles import evaluate_task_oracle
from tests.test_context_recovery_oracle import ARTIFACTS, TASK_ID, _case, _sync_output

JOURNEY = "benchmarks/fixtures/cross-harness/context-recovery/journeys.json"


@pytest.mark.parametrize(("mutation", "codes"), [
    ("unreported_added_parallel_file", ["unexpected_workspace_effect"]),
    ("unreported_duplicate_journey_state", ["unexpected_workspace_effect"]),
    ("duplicate_journey_file_changed", ["duplicate_effect_not_idempotent"]),
    ("no_existing_journey_state", ["journey_state_mismatch"]),
    ("native_resume_claim", ["native_full_session_claim"]),
    ("negated_next_action", ["next_action_mismatch"]),
    ("boolean_journey_count", ["duplicate_effect_not_idempotent"]),
    ("unreported_added_report_file", ["unexpected_workspace_effect"]),
    ("negated_next_action_after_phrase", ["next_action_mismatch"]),
    ("paraphrased_native_state_claim", ["canonical_markdown_mismatch"]),
])
def test_context_recovery_rejects_independent_review_counterexamples(tmp_path: Path, mutation: str, codes: list[str]) -> None:
    context, report, _ = _case(tmp_path)
    workspace = Path(context.scorecard_core["workspace_root"])
    if mutation == "unreported_added_parallel_file":
        extra = workspace / "benchmarks/fixtures/cross-harness/context-recovery/parallel/unapproved-note.md"
        extra.write_text("Unrequested change to parallel-owned workspace.\n", encoding="utf-8", newline="\n")
    elif mutation == "unreported_duplicate_journey_state":
        extra = workspace / "journeys.json"
        extra.write_text(json.dumps({"journeys": [
            {"id": "first", "continuation": "cpv_context_recovery_v1"},
            {"id": "duplicate", "continuation": "cpv_context_recovery_v1"},
        ]}, sort_keys=True), encoding="utf-8")
    elif mutation == "duplicate_journey_file_changed":
        (workspace / JOURNEY).write_text(json.dumps({"journeys": [
            {"id": "first", "continuation": "cpv_context_recovery_v1"},
            {"id": "duplicate", "continuation": "cpv_context_recovery_v1"},
        ]}, sort_keys=True), encoding="utf-8")
    elif mutation == "no_existing_journey_state":
        (workspace / JOURNEY).unlink()
    elif mutation == "native_resume_claim":
        context.artifact_paths[ARTIFACTS[1]].write_text(
            f"# {TASK_ID}\nI restored the entire native full-session resume, including all hidden provider state.\n",
            encoding="utf-8",
            newline="\n",
        )
    elif mutation == "negated_next_action":
        report["next_action"]["description"] = "Do not perform private continuation context. Discard source-bound preview."
    elif mutation == "boolean_journey_count":
        report["duplicate_resolutions"][0]["journey_count"] = True
    elif mutation == "unreported_added_report_file":
        extra = workspace / "benchmarks/fixtures/cross-harness/context-recovery/reports/extra.md"
        extra.write_text("Unapproved write outside the submitted workspace_state.\n", encoding="utf-8", newline="\n")
    elif mutation == "negated_next_action_after_phrase":
        report["next_action"]["description"] = (
            "private continuation context is prohibited. "
            "source-bound preview must be abandoned."
        )
    elif mutation == "paraphrased_native_state_claim":
        context.artifact_paths[ARTIFACTS[1]].write_text(
            f"# {TASK_ID}\nAll conversation memory and private provider execution state have been restored completely.\n",
            encoding="utf-8",
            newline="\n",
        )
    _sync_output(context, report)
    result = evaluate_task_oracle(context)
    assert result.state == "fail"
    for code in codes:
        assert code in result.failure_codes
