import json

from scripts.run_huggingface_release_stage import build_stage, render_markdown


def test_huggingface_release_stage_blocks_upload_without_complete_release_gates():
    readiness = {
        "schema": "harness.model-release-readiness/v1",
        "models": [
            {
                "model": "14B",
                "root": "E:/local-model-run/14B",
                "root_exists": True,
                "weight_file_count": 1,
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
                "blockers": ["No benchmark artifact is attached to the release row."],
                "release_gates": [
                    {"gate_id": "root_exists", "passed": True},
                    {"gate_id": "weights_present", "passed": True},
                    {"gate_id": "file:checksums.sha256", "passed": False},
                    {"gate_id": "benchmark_evidence_present", "passed": False},
                ],
            }
        ],
    }

    stage = build_stage(
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

    assert stage["schema"] == "harness.huggingface-release-stage/v1"
    assert stage["summary"]["ready_to_upload_models"] == 0
    assert stage["summary"]["do_not_upload_models"] == 1
    assert stage["models"][0]["repo_id"] == "HarperZ9/flywheel-local-coder-14b"
    assert stage["models"][0]["upload_status"] == "DO_NOT_UPLOAD"


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
