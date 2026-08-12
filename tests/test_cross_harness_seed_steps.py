import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.cross_harness_artifacts import bind_attempt_receipt, canonical_sha256
from harness.cross_harness_cli import _apply_admission
from harness.cross_harness_executor import SHARED_TOOL_POLICY
from harness.cross_harness_seed_steps import build_cross_harness_steps
from scripts.run_closed_loop_benchmark_seed import OrchestrationStep, main as seed_main, run_step


FULL_IDS = {
    "agt-001": "agt-001-index-fallback-integrity",
    "agt-003": "agt-003-codex-flywheel-shared-task",
    "agt-009": "agt-009-receipts-vs-guardrails-friction",
    "agt-010": "agt-010-documentation-schematic-maintenance",
}
ROLES = ["codex_harness", "flywheel_harness", "local_14b", "local_32b"]


def _args(tmp_path):
    return SimpleNamespace(
        python=sys.executable,
        cross_harness_manifest=str(tmp_path / "manifest.json"),
        cross_harness_runtime_matrix=str(tmp_path / "runtime.json"),
        cross_harness_endpoint_gate=str(tmp_path / "gate.json"),
        cross_harness_gate_run_id="gate-1",
        cross_harness_max_gate_age_seconds=900,
        cross_harness_source_commit="abc123",
        cross_harness_source_root=str(tmp_path / "source"),
        cross_harness_attempt_timeout_seconds=300,
        benchmark_timeout_seconds=10800,
    )


def test_cross_harness_steps_are_ordered_bounded_and_bind_child_run_roots(tmp_path):
    steps = build_cross_harness_steps(_args(tmp_path), run_id="pilot", artifact_dir=tmp_path)

    assert [step.step_id for step in steps] == [
        "cross_harness_admission", "cross_harness_local", "cross_harness_spark"]
    admission, local, spark = steps
    assert [admission.command[admission.command.index("--tasks") + 1], admission.command[admission.command.index("--repetitions") + 1]] == ["agt-001,agt-003", "1"]
    assert [local.command[local.command.index("--roles") + 1], local.command[local.command.index("--repetitions") + 1]] == ["local_14b,local_32b", "1"]
    assert [spark.command[spark.command.index("--roles") + 1], spark.command[spark.command.index("--repetitions") + 1]] == ["codex_harness,flywheel_harness", "3"]
    admission_receipt = str(tmp_path / "admission-smoke" / "pilot-admission" / "run.json")
    assert local.command[local.command.index("--admission-receipt") + 1] == admission_receipt
    assert spark.command[spark.command.index("--admission-receipt") + 1] == admission_receipt
    assert "--endpoint-gate" in local.command and "--gate-run-id" in local.command
    assert all("84" not in token for step in steps for token in step.command)
    assert admission.expected_artifacts == [
        admission_receipt,
        str(tmp_path / "admission-smoke" / "pilot-admission" / "comparison-input.json"),
        str(tmp_path / "admission-smoke" / "pilot-admission" / "artifact-index.json"),
    ]


def test_cross_harness_execution_ignores_legacy_manifest_provider_roles(tmp_path):
    args = _args(tmp_path); args.cross_harness_provider_roles = "dry"
    commands = [step.command for step in build_cross_harness_steps(args, run_id="pilot", artifact_dir=tmp_path)]
    assert commands[0][commands[0].index("--roles") + 1] == "codex_harness,flywheel_harness,local_14b,local_32b"


def test_executor_plan_projects_benchmark_identity_into_every_row(tmp_path):
    from harness.cross_harness_executor import expand_attempt_rows
    manifest = _manifest()
    for task in manifest["task_rows"]:
        task.update(benchmark_id="cross_harness_reproducibility_matrix", coverage_unit=task["task_id"])

    matrix = {"runtime_rows": [{"provider_role": "codex_harness", "focused_run_ready": True,
                                "blocking_gates": []}]}
    rows = expand_attempt_rows(manifest, matrix, artifact_root=tmp_path, selectors=["agt-001"],
                               roles=["codex_harness"], repetitions=1, run_id="run", phase="spark")

    assert rows[0]["benchmark_id"] == "cross_harness_reproducibility_matrix"
    assert rows[0]["coverage_unit"] == FULL_IDS["agt-001"]


def test_run_step_records_utc_hashes_exit_code_and_only_environment_names(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK7_SECRET_NAME", "must-not-appear")
    monkeypatch.setenv("TASK7_SAFE_NAME", "safe-value-must-not-appear")
    step = OrchestrationStep("probe", "ledger probe", [sys.executable, "-c", "import sys;print('out');print('err',file=sys.stderr)"], 10, [])

    result = run_step(step, cwd=tmp_path, log_dir=tmp_path / "logs")

    assert result["exit_code"] == 0
    assert result["stdout_sha256"] == hashlib.sha256(Path(result["stdout_path"]).read_bytes()).hexdigest()
    assert result["stderr_sha256"] == hashlib.sha256(Path(result["stderr_path"]).read_bytes()).hexdigest()
    assert datetime.fromisoformat(result["started_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(result["finished_at"].replace("Z", "+00:00"))
    assert "TASK7_SECRET_NAME" not in result["environment_names"]
    assert "TASK7_SAFE_NAME" in result["environment_names"]
    assert "must-not-appear" not in json.dumps(result)
    assert "safe-value-must-not-appear" not in json.dumps(result)


def test_cross_harness_only_cli_short_circuits_legacy_deck(tmp_path, capsys):
    out = tmp_path / "seed.json"
    args = _args(tmp_path)
    argv = ["--cross-harness-only", "--cross-harness-run-id", "pilot", "--dry-plan", "--artifact-dir", str(tmp_path), "--out", str(out)]
    for flag, value in (
        ("--python", args.python), ("--cross-harness-manifest", args.cross_harness_manifest),
        ("--cross-harness-runtime-matrix", args.cross_harness_runtime_matrix),
        ("--cross-harness-endpoint-gate", args.cross_harness_endpoint_gate),
        ("--cross-harness-gate-run-id", args.cross_harness_gate_run_id),
        ("--cross-harness-source-commit", args.cross_harness_source_commit),
        ("--cross-harness-source-root", args.cross_harness_source_root),
    ): argv.extend((flag, value))

    assert seed_main(argv) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [row["step_id"] for row in report["planned_steps"]] == [
        "cross_harness_admission", "cross_harness_local", "cross_harness_spark"]
    assert report["summary"]["artifact_paths"] == [path for row in report["planned_steps"] for path in row["expected_artifacts"]]
    assert report["planned_steps"][-1]["expected_artifacts"][1] == str(tmp_path / "spark-pilot/pilot-spark/comparison-input.json")
    capsys.readouterr()


def _manifest():
    tasks = [{"task_id": full, "raw_prompt_sha256": key[-3:] * 21 + "a", "input_sha256s": {}, "oracle": {"checker_id": key}}
             for key, full in FULL_IDS.items()]
    specs = [{"provider_role": role, "harness_id": "direct" if role == "codex_harness" else "router",
              "adapter_id": "adapter", "target_model": "model"} for role in ROLES]
    return {"task_set_id": "set", "task_rows": tasks, "provider_specs": specs}


def _current():
    return {"source_commit": "commit", "source_snapshot_sha256": "s" * 64,
            "cache_state": "cold_declared", "execution_mode": "focused_run"}


def _admission(tmp_path, *, mutate=None):
    manifest, current, rows = _manifest(), _current(), []
    root = tmp_path / "admission" / "admission-run"; root.mkdir(parents=True)
    for role in ROLES:
        spec = next(item for item in manifest["provider_specs"] if item["provider_role"] == role)
        for selector in ("agt-001", "agt-003"):
            task = next(item for item in manifest["task_rows"] if item["task_id"] == FULL_IDS[selector])
            attempt = root / f"{role}-{selector}"; attempt.mkdir(); receipt = attempt / "receipt.json"
            row = {"phase": "admission-smoke", "provider_role": role, "task_id": task["task_id"], "repetition": 1,
                   "primary_outcome": "completed", "receipt_path": str(receipt), "task_set_id": "set",
                   "raw_prompt_sha256": task["raw_prompt_sha256"], "input_sha256s": {}, "harness_id": spec["harness_id"],
                   "adapter_id": "adapter", "model_id": "model", "tool_policy_sha256": canonical_sha256(SHARED_TOOL_POLICY),
                   **current, "availability_evidence": {"adapter_evidence": {"oracle_spec_sha256": canonical_sha256(task["oracle"])}}}
            rows.append(row)
    if mutate: mutate(rows)
    for row in rows:
        receipt = Path(row["receipt_path"]); receipt.parent.mkdir(parents=True, exist_ok=True)
        bind_attempt_receipt(row, {}, receipt)
    path = root / "run.json"
    path.write_text(json.dumps({"schema": "harness.cross-harness-run-receipt/v1", "phase": "admission-smoke", "rows": rows}), encoding="utf-8")
    return manifest, current, path


@pytest.mark.parametrize(("selectors", "roles", "repetitions"), [
    (["agt-001", "agt-003", "agt-009", "agt-010"], ["local_14b", "local_32b"], 1),
    (["agt-001", "agt-003", "agt-009", "agt-010"], ["codex_harness", "flywheel_harness"], 3),
])
def test_admission_smoke_is_canonical_not_later_phase_selection(tmp_path, selectors, roles, repetitions):
    manifest, current, receipt = _admission(tmp_path)
    matrix = {"runtime_rows": [{"provider_role": role, "focused_run_ready": True, "blocking_gates": []} for role in roles]}

    _apply_admission(matrix, receipt, manifest, selectors, roles, repetitions, current=current)

    assert all(row["focused_run_ready"] for row in matrix["runtime_rows"])


@pytest.mark.parametrize("mutate", [
    lambda rows: rows.pop(0),
    lambda rows: rows.append(dict(rows[0], receipt_path=rows[0]["receipt_path"] + "-duplicate")),
    lambda rows: rows.append(dict(rows[0], task_id=FULL_IDS["agt-009"], receipt_path=rows[0]["receipt_path"] + "-extra")),
    lambda rows: rows[0].update(repetition=2),
    lambda rows: rows[0].update(phase="local"),
])
def test_admission_rejects_noncanonical_selected_role_shape(tmp_path, mutate):
    manifest, current, receipt = _admission(tmp_path, mutate=mutate)
    matrix = {"runtime_rows": [{"provider_role": "codex_harness", "focused_run_ready": True, "blocking_gates": []}]}

    _apply_admission(matrix, receipt, manifest, ["agt-009"], ["codex_harness"], 7, current=current)

    assert matrix["runtime_rows"][0]["blocking_gates"] == ["admission_selection_mismatch"]


def test_unrelated_failed_role_does_not_poison_requested_role_but_harness_drift_does(tmp_path):
    def mutate(rows):
        next(row for row in rows if row["provider_role"] == "local_14b")["primary_outcome"] = "failed"
        next(row for row in rows if row["provider_role"] == "codex_harness")["harness_id"] = "drift"
    manifest, current, receipt = _admission(tmp_path, mutate=mutate)
    matrix = {"runtime_rows": [{"provider_role": role, "focused_run_ready": True, "blocking_gates": []}
                               for role in ("codex_harness", "flywheel_harness")]}

    _apply_admission(matrix, receipt, manifest, ["agt-009"], ["codex_harness", "flywheel_harness"], 3, current=current)

    assert matrix["runtime_rows"][0]["blocking_gates"] == ["admission_adapter_mismatch"]
    assert matrix["runtime_rows"][1]["focused_run_ready"] is True


@pytest.mark.parametrize("break_manifest", [
    lambda rows: rows.pop(0),
    lambda rows: rows.pop(1),
    lambda rows: rows.append(dict(rows[0], task_id=rows[0]["task_id"] + "-ambiguous")),
])
def test_missing_or_ambiguous_canonical_smoke_task_blocks_all_requested_roles(tmp_path, break_manifest):
    manifest, current, receipt = _admission(tmp_path)
    break_manifest(manifest["task_rows"])
    for selectors, repetitions in ((["agt-001"], 1), (["agt-009"], 3)):
        matrix = {"runtime_rows": [{"provider_role": role, "focused_run_ready": True, "blocking_gates": []}
                                   for role in ("codex_harness", "flywheel_harness")]}
        _apply_admission(matrix, receipt, manifest, selectors, ["codex_harness", "flywheel_harness"], repetitions, current=current)
        assert [row["blocking_gates"] for row in matrix["runtime_rows"]] == [
            ["admission_selection_mismatch"], ["admission_selection_mismatch"]]
