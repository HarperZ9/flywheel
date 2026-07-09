import json

from scripts.run_model_repo_stage import build_stage, render_markdown


def test_model_repo_stage_creates_required_metadata_files(tmp_path):
    docs = tmp_path / "docs" / "14B"
    docs.mkdir(parents=True)
    for name in ["README.md", "MODEL_CARD.md", "USAGE.md", "SAFETY-ACCOUNTABILITY.md", "RELEASE-CHECKLIST.md"]:
        (docs / name).write_text(f"# {name}\n", encoding="utf-8")
    root = tmp_path / "model"
    root.mkdir()
    (root / "LICENSE").write_text("license\n", encoding="utf-8")
    readiness = {
        "models": [
            {
                "model": "14B",
                "root": str(root),
                "weight_file_count": 1,
                "weight_total_size_bytes": 123,
                "endpoint_profiles": [{"profile_id": "serve-14b"}],
                "benchmark_artifact_count": 0,
            }
        ]
    }
    publish = {
        "models": [
            {
                "model": "14B",
                "candidate_name": "Flywheel-Local-Coder-14B",
                "candidate_slug": "flywheel-local-coder-14b",
                "publish_status": "DO_NOT_PUBLISH",
                "blockers": ["benchmark missing"],
            }
        ]
    }

    stage = build_stage(
        readiness=readiness,
        publish_plan=publish,
        readiness_artifact="readiness.json",
        publish_plan_artifact="publish.json",
        docs_root=tmp_path / "docs",
        stage_root=tmp_path / "stage",
        namespace="HarperZ9",
        sync_to_model_root=False,
    )

    model = stage["models"][0]
    assert stage["schema"] == "harness.model-repo-stage/v1"
    assert model["required_files_present"] == 10
    assert model["required_files_missing"] == []
    assert (tmp_path / "stage" / "flywheel-local-coder-14b" / "provenance.json").exists()
    assert (tmp_path / "stage" / "flywheel-local-coder-14b" / "checksums.sha256").exists()


def test_model_repo_stage_markdown_summarizes_repo_ids():
    stage = {
        "schema": "harness.model-repo-stage/v1",
        "stage_root": "C:/tmp/stage",
        "namespace": "HarperZ9",
        "secret_policy": "metadata-only",
        "summary": {
            "required_files_present": 20,
            "required_files": 20,
            "synced_files": 0,
            "ready_to_upload_after_operator_approval": 0,
            "do_not_upload_models": 2,
        },
        "models": [
            {
                "model": "32B",
                "repo_id": "HarperZ9/flywheel-local-coder-32b",
                "stage_root": "C:/tmp/stage/flywheel-local-coder-32b",
                "required_files_present": 10,
                "required_files": ["README.md"],
                "upload_status": "DO_NOT_UPLOAD",
            }
        ],
    }

    markdown = render_markdown(json.loads(json.dumps(stage)))

    assert "# Model repository staging" in markdown
    assert "HarperZ9/flywheel-local-coder-32b" in markdown
