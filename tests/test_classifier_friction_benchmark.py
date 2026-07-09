import json

from harness.classifier_friction_bench import TASKS, build_report, run_case
from scripts.run_classifier_friction_benchmark import main


class FakeBackend:
    name = "fake"
    model = "fake-model"

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        del messages, system, max_tokens, temperature, seed
        return {
            "text": (
                "Scope and assumptions are labeled. The remediation plan includes "
                "triage, owner handoff, validation tests, rollback, audit receipt, "
                "public ticket boundaries, credentials to avoid, and verification evidence."
            ),
            "model_ref": "fake:model",
        }


def test_run_case_emits_coverage_and_receipt_metric_fields():
    row = run_case(
        TASKS[0],
        FakeBackend(),
        provider="serve",
        mode="accountability_first",
        seed=1,
        timeout_seconds=30,
        max_tokens=200,
    )

    assert row["coverage_unit"] == "enterprise_vuln_triage_safe:accountability_first"
    assert row["provider_role"] == "flywheel"
    assert 0.0 <= row["quality_score"] <= 1.0
    assert "latency_ms" in row
    assert "failure_class" in row
    assert row["receipt_hash"] == row["receipt"]


def test_build_report_exposes_classifier_friction_benchmark_id():
    row = run_case(
        TASKS[0],
        FakeBackend(),
        provider="codex",
        mode="guardrail_off",
        seed=1,
        timeout_seconds=30,
        max_tokens=200,
    )

    report = build_report(
        provider_order=["codex"],
        mode_order=["guardrail_off"],
        results=[row],
    )

    assert report["schema"] == "classifier-friction-benchmark/v1"
    assert report["benchmark_id"] == "classifier_friction_accountability"
    assert report["coverage_units"] == ["enterprise_vuln_triage_safe:guardrail_off"]


def test_runner_writes_deterministic_outputs_and_store_receipt(tmp_path):
    out = tmp_path / "classifier.json"
    md = tmp_path / "classifier.md"
    store = tmp_path / "store"

    result = main([
        "--providers",
        "dry",
        "--max-tasks",
        "1",
        "--out",
        str(out),
        "--markdown-out",
        str(md),
        "--store-root",
        str(store),
        "--run-id",
        "run_classifier",
    ])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert result == 0
    assert data["schema"] == "classifier-friction-benchmark/v1"
    assert data["artifacts"]["json"] == str(out.resolve())
    assert md.exists()
    assert data["store_outputs"][0]["schema"] == "harness.receipt/v1"
