import json

from scripts.run_model_publish_plan import build_plan, main, publish_row


def ready_model_row():
    return {
        "model": "14B",
        "model_key": "14b",
        "root": "E:/local-model-run/models/Qwen2.5-Coder-14B-Instruct",
        "root_exists": True,
        "trained": True,
        "trained_artifact_present": True,
        "weight_file_count": 1,
        "release_doc_score": 1.0,
        "endpoint_profile_count": 1,
        "endpoint_gate_generation_ok_count": 1,
        "benchmark_artifact_count": 1,
        "enterprise_release_ready": True,
        "verdict": "MODEL_RELEASE_READY_STATIC",
        "gates": {
            "identity": {"present_files": ["MODEL_CARD.md", "README.md", "LICENSE"], "missing_files": []},
            "integrity": {"present_files": ["checksums.sha256", "provenance.json"], "missing_files": []},
            "serving": {"present_files": ["endpoint.json", "usage.md"], "missing_files": []},
            "evaluation": {"present_files": ["benchmark-summary.json", "safety.md", "release-checklist.md"], "missing_files": []},
        },
    }


def test_publish_row_names_model_but_does_not_publish_when_gates_missing():
    row = ready_model_row()
    row["endpoint_gate_generation_ok_count"] = 0

    plan_row = publish_row(row, name_prefix="Flywheel-Local-Coder")

    assert plan_row["candidate_name"] == "Flywheel-Local-Coder-14B"
    assert plan_row["candidate_slug"] == "flywheel-local-coder-14b"
    assert plan_row["publish_status"] == "DO_NOT_PUBLISH"
    assert "No endpoint generation gate has passed." in plan_row["blockers"]


def test_build_plan_marks_ready_models_ready_to_stage_only():
    plan = build_plan(
        {"schema": "harness.model-release-readiness/v1", "models": [ready_model_row()]},
        readiness_artifact="model_release.json",
    )

    assert plan["schema"] == "harness.model-publish-plan/v1"
    assert plan["models"][0]["publish_status"] == "READY_TO_STAGE"
    assert len(plan["models"][0]["release_gates"]) == 17
    assert plan["models"][0]["release_gates"][0]["gate_id"] == "trained_artifact_present"
    assert plan["models"][0]["release_gates"][0]["passed"] is True
    assert plan["summary"]["ready_to_stage_models"] == 1
    assert "No model is published" in plan["publish_policy"]


def test_publish_row_blocks_untrained_track_with_no_republish_blocker():
    row = ready_model_row()
    row["model"] = "32B"
    row["trained"] = False
    row["trained_artifact_present"] = False

    plan_row = publish_row(row, name_prefix="Flywheel-Local-Coder")

    first_gate = plan_row["release_gates"][0]
    assert first_gate["gate_id"] == "trained_artifact_present"
    assert first_gate["passed"] is False
    assert plan_row["publish_status"] == "DO_NOT_PUBLISH"
    assert (
        "No trained model artifact exists for this track; "
        "base weights must not be republished under a Flywheel name."
    ) in plan_row["blockers"]
    p0_actions = [action for action in plan_row["actions"] if action["priority"] == "P0"]
    assert any(
        action["acceptance_gate"] == "`trained_artifact_present` passes in the next publish plan."
        for action in p0_actions
    )


def test_build_plan_missing_readiness_artifact_is_unverifiable():
    plan = build_plan(
        {"schema": "", "models": []},
        readiness_artifact="missing.json",
        source_loaded=False,
        source_load_error="missing_artifact",
    )

    assert plan["summary"]["source_loaded"] is False
    assert plan["summary"]["source_ready"] is False
    assert plan["summary"]["ready_to_stage_models"] == 0


def test_main_writes_publish_plan_and_store_receipt(tmp_path):
    readiness = tmp_path / "model_release.json"
    readiness.write_text(json.dumps({
        "schema": "harness.model-release-readiness/v1",
        "models": [ready_model_row()],
    }), encoding="utf-8")
    out = tmp_path / "publish_plan.json"
    md = tmp_path / "publish_plan.md"
    store = tmp_path / "store"

    code = main([
        "--release-readiness-artifact",
        str(readiness),
        "--out",
        str(out),
        "--markdown-out",
        str(md),
        "--store-root",
        str(store),
        "--run-id",
        "run_models",
    ])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert data["summary"]["candidate_names"] == ["Flywheel-Local-Coder-14B"]
    assert data["store_outputs"][0]["schema"] == "harness.receipt/v1"
    assert "# Model naming and publication plan" in md.read_text(encoding="utf-8")
