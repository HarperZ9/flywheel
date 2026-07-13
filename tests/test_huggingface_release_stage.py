import json

from scripts.run_huggingface_release_stage import build_stage, render_markdown


def _build_stage(readiness, publish_plan):
    return build_stage(
        readiness=readiness,
        publish_plan=publish_plan,
        readiness_artifact="readiness.json",
        publish_plan_artifact="publish.json",
        readiness_loaded=True,
        publish_plan_loaded=True,
        readiness_load_error="",
        publish_plan_load_error="",
        namespace="HarperZ9",
        private=False,
        operator_upload_approved=False,
    )


def test_huggingface_release_stage_blocks_upload_without_complete_release_gates():
    readiness = {
        "schema": "harness.model-release-readiness/v1",
        "models": [
            {
                "model": "14B",
                "root": "E:/local-model-run/14B",
                "root_exists": True,
                "weight_file_count": 1,
                "trained": True,
                "trained_artifact_present": True,
            }
        ],
    }
    publish_plan = {
        "schema": "harness.model-publish-plan/v1",
        "models": [
            {
                "model": "14B",
                "candidate_name": "Flywheel-Local-Coder-14B",
                "candidate_slug": "flywheel-local-coder-14b",
                "root": "E:/local-model-run/14B",
                "publish_status": "DO_NOT_PUBLISH",
                "trained": True,
                "trained_artifact_present": True,
                "blockers": ["No benchmark artifact is attached to the release row."],
                "release_gates": [
                    {"gate_id": "trained_artifact_present", "passed": True},
                    {"gate_id": "root_exists", "passed": True},
                    {"gate_id": "weights_present", "passed": True},
                    {"gate_id": "file:checksums.sha256", "passed": False},
                    {"gate_id": "benchmark_evidence_present", "passed": False},
                ],
            }
        ],
    }

    stage = _build_stage(readiness, publish_plan)

    assert stage["schema"] == "harness.huggingface-release-stage/v1"
    assert stage["summary"]["ready_to_upload_models"] == 0
    assert stage["summary"]["do_not_upload_models"] == 1
    assert stage["models"][0]["repo_id"] == "HarperZ9/flywheel-local-coder-14b"
    assert stage["models"][0]["upload_status"] == "DO_NOT_UPLOAD"
    assert len(stage["models"][0]["stage_gates"]) == 8
    assert stage["models"][0]["stage_gates"][0]["gate_id"] == "trained_artifact_present"
    assert stage["models"][0]["stage_gates"][0]["passed"] is True


def test_huggingface_release_stage_untrained_track_emits_do_not_upload_templates():
    readiness = {
        "schema": "harness.model-release-readiness/v1",
        "models": [
            {
                "model": "32B",
                "root": "E:/local-model-run/models/Qwen2.5-Coder-32B-Instruct",
                "root_exists": True,
                "weight_file_count": 1,
                "trained": False,
                "trained_artifact_present": False,
            }
        ],
    }
    publish_plan = {
        "schema": "harness.model-publish-plan/v1",
        "models": [
            {
                "model": "32B",
                "candidate_name": "Flywheel-Local-Coder-32B",
                "candidate_slug": "flywheel-local-coder-32b",
                "root": "E:/local-model-run/models/Qwen2.5-Coder-32B-Instruct",
                "publish_status": "DO_NOT_PUBLISH",
                "trained": False,
                "trained_artifact_present": False,
                "blockers": [
                    "No trained model artifact exists for this track; "
                    "base weights must not be republished under a Flywheel name."
                ],
                "release_gates": [{"gate_id": "trained_artifact_present", "passed": False}],
            }
        ],
    }

    stage = _build_stage(readiness, publish_plan)

    model = stage["models"][0]
    templates = model["upload_templates"]
    assert model["upload_status"] == "DO_NOT_UPLOAD"
    assert model["trained_artifact_present"] is False
    assert templates["cli"].startswith("# DO NOT UPLOAD")
    assert templates["python"].startswith("# DO NOT UPLOAD")
    assert "hf upload" not in templates["cli"]
    assert "hf upload" not in templates["python"]
    assert "upload_folder" not in templates["python"]


def test_huggingface_release_stage_trained_track_emits_real_upload_templates():
    model_root = "E:/local-model-run/release/flywheel-local-coder-14b"
    readiness = {
        "schema": "harness.model-release-readiness/v1",
        "models": [
            {
                "model": "14B",
                "root": model_root,
                "root_exists": True,
                "weight_file_count": 1,
                "trained": True,
                "trained_artifact_present": True,
            }
        ],
    }
    publish_plan = {
        "schema": "harness.model-publish-plan/v1",
        "models": [
            {
                "model": "14B",
                "candidate_name": "Flywheel-Local-Coder-14B",
                "candidate_slug": "flywheel-local-coder-14b",
                "root": model_root,
                "publish_status": "READY_TO_STAGE",
                "trained": True,
                "trained_artifact_present": True,
                "blockers": [],
                "release_gates": [
                    {"gate_id": "trained_artifact_present", "passed": True},
                    {"gate_id": "file:checksums.sha256", "passed": True},
                    {"gate_id": "benchmark_evidence_present", "passed": True},
                ],
            }
        ],
    }

    stage = _build_stage(readiness, publish_plan)

    templates = stage["models"][0]["upload_templates"]
    assert not templates["cli"].startswith("# DO NOT UPLOAD")
    assert "hf upload HarperZ9/flywheel-local-coder-14b" in templates["cli"]
    assert model_root in templates["cli"]
    assert model_root in templates["python"]
    assert "upload_folder" in templates["python"]


def test_huggingface_release_stage_markdown_includes_templates():
    stage = {
        "schema": "harness.huggingface-release-stage/v1",
        "upload_mode": "dry_run_metadata_only",
        "namespace": "HarperZ9",
        "private": False,
        "publication_policy": "No upload.",
        "summary": {
            "models": 1,
            "ready_to_upload_models": 0,
            "waiting_for_operator_upload_approval": 0,
            "do_not_upload_models": 1,
        },
        "source_references": [{"label": "Hub", "url": "https://huggingface.co/docs/huggingface_hub/guides/cli"}],
        "models": [
            {
                "model": "32B",
                "candidate_name": "Flywheel-Local-Coder-32B",
                "repo_id": "HarperZ9/flywheel-local-coder-32b",
                "upload_status": "DO_NOT_UPLOAD",
                "blockers": ["blocked"],
                "upload_templates": {
                    "cli": "hf upload HarperZ9/flywheel-local-coder-32b E:/local-model-run/32B --repo-type model",
                    "python": "from huggingface_hub import HfApi",
                },
            }
        ],
    }

    markdown = render_markdown(json.loads(json.dumps(stage)))

    assert "# Hugging Face release staging" in markdown
    assert "hf upload HarperZ9/flywheel-local-coder-32b" in markdown
    assert "https://huggingface.co/docs/huggingface_hub/guides/cli" in markdown
