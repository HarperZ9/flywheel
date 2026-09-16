import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


def _routing_collection():
    try:
        return importlib.import_module("harness.routing_collection")
    except ModuleNotFoundError as exc:
        pytest.fail(f"routing collection helper module is missing: {exc}")


def test_builtin_split_plan_is_retrospective_diagnostic_only():
    rc = _routing_collection()
    plan = rc.build_builtin_split_plan(
        tier="easy",
        task_ids=["add_two", "max_of_three"],
        split_id="routing-test",
    )

    assert plan["schema"] == "m7-routing-split-plan/v1"
    assert plan["split_family"] == "retrospective_diagnostic"
    assert plan["fresh_task_family_manifest"] is None
    assert plan["future_fresh_task_family_status"] == "unavailable_in_builtin_m7_path"
    assert plan["plan_written_before_generation"] is True
    assert plan["ordering_proof_only"] is True
    assert any("does not prove independent preregistration" in item
               for item in plan["does_not_prove"])
    assert {row["role"] for row in plan["tasks"]} == {"retrospective_diagnostic"}
    assert {row["freshness"] for row in plan["tasks"]} == {"historical_visible"}


def test_collection_artifact_labels_measurement_denominators_and_hashes():
    rc = _routing_collection()
    split_plan = rc.build_builtin_split_plan(
        tier="easy",
        task_ids=["add_two"],
        split_id="routing-test",
    )
    split_hash = rc.canonical_sha256(split_plan)
    reports = {
        "single_shot": {
            "per_task_detail": [{
                "task_id": "add_two",
                "arm_name": "single_shot",
                "candidate_rows": [],
            }]
        }
    }

    artifact = rc.build_collection_artifact(
        run_id="run-x",
        tier="easy",
        source_commit="abc123",
        split_plan=split_plan,
        split_plan_sha256=split_hash,
        split_plan_path="split.json",
        reports=reports,
    )

    assert artifact["schema"] == "m7-routing-collection/v1"
    assert artifact["split_plan"]["sha256"] == split_hash
    assert artifact["split_plan"]["scope"] == "ordering_only"
    assert artifact["measurement_denominators"]["generation_latency_ms"].startswith(
        "time.perf_counter_ns around proposer.generate")
    assert artifact["unavailable_metric_policy"].startswith("null plus explicit provenance")
    assert artifact["rows"][0]["split_assignment"]["role"] == "retrospective_diagnostic"


def test_collection_artifact_fails_closed_for_unknown_report_task():
    rc = _routing_collection()
    split_plan = rc.build_builtin_split_plan(
        tier="easy",
        task_ids=["add_two"],
        split_id="routing-test",
    )
    reports = {"single_shot": {"per_task_detail": [{"task_id": "not_in_plan"}]}}

    with pytest.raises(ValueError, match="not_in_plan"):
        rc.build_collection_artifact(
            run_id="run-x",
            tier="easy",
            source_commit="abc123",
            split_plan=split_plan,
            split_plan_sha256=rc.canonical_sha256(split_plan),
            split_plan_path="split.json",
            reports=reports,
        )


def test_collection_artifact_fails_closed_for_duplicate_plan_rows():
    rc = _routing_collection()
    split_plan = rc.build_builtin_split_plan(
        tier="easy",
        task_ids=["add_two"],
        split_id="routing-test",
    )
    split_plan["tasks"].append(dict(split_plan["tasks"][0]))
    reports = {"single_shot": {"per_task_detail": [{"task_id": "add_two"}]}}

    with pytest.raises(ValueError, match="duplicate"):
        rc.build_collection_artifact(
            run_id="run-x",
            tier="easy",
            source_commit="abc123",
            split_plan=split_plan,
            split_plan_sha256=rc.canonical_sha256(split_plan),
            split_plan_path="split.json",
            reports=reports,
        )


def test_run_m7_eval_dry_run_writes_opt_in_routing_collection(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    scorecard = tmp_path / "m7.json"
    collection = tmp_path / "routing.json"
    split_plan = tmp_path / "split.json"
    workroot = tmp_path / "work"

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_m7_eval.py",
            "--dry-run",
            "--n-tasks", "1",
            "--out", str(scorecard),
            "--workroot", str(workroot),
            "--routing-collection-out", str(collection),
            "--routing-split-plan-out", str(split_plan),
            "--routing-split-id", "unit-routing",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert scorecard.exists()
    assert collection.exists()
    assert split_plan.exists()

    scorecard_data = json.loads(scorecard.read_text(encoding="utf-8"))
    collection_data = json.loads(collection.read_text(encoding="utf-8"))
    split_data = json.loads(split_plan.read_text(encoding="utf-8"))

    assert scorecard_data["meta"]["routing_collection"]["path"] == str(collection)
    assert scorecard_data["meta"]["routing_split_plan"]["path"] == str(split_plan)
    assert split_data["split_family"] == "retrospective_diagnostic"
    assert collection_data["split_plan"]["scope"] == "ordering_only"
    assert collection_data["rows"]
    assert collection_data["rows"][0]["split_assignment"]["role"] == "retrospective_diagnostic"
