from pathlib import Path

from scripts.run_model_release_readiness import build_report, profile_model, split_names


def test_split_names_handles_empty_items():
    assert split_names("14B, 32B,,") == ["14B", "32B"]


def test_profile_model_reports_static_release_gaps_without_reading_contents(tmp_path):
    root = tmp_path / "14B"
    root.mkdir()
    (root / "model.gguf").write_bytes(b"weights")
    (root / "MODEL_CARD.md").write_text("do-not-read", encoding="utf-8")
    (root / "README.md").write_text("do-not-read", encoding="utf-8")

    row = profile_model(
        "14B",
        base_root=tmp_path,
        explicit_root=None,
        artifact_roots=[],
        endpoint_profiles=[],
        endpoint_gate_rows=[],
        max_entries=50,
    )

    assert row["model"] == "14B"
    assert row["root_exists"] is True
    assert row["content_read"] is False
    assert row["weight_file_count"] == 1
    assert row["enterprise_release_ready"] is False
    assert row["verdict"] == "MODEL_ARTIFACTS_WITH_RELEASE_GAPS"
    assert "checksums.sha256" in row["gates"]["integrity"]["missing_files"]
    assert "do-not-read" not in str(row)


def test_profile_model_finds_known_qwen_model_directory_under_models(tmp_path):
    root = tmp_path / "models" / "Qwen2.5-Coder-14B-Instruct"
    root.mkdir(parents=True)
    (root / "model.gguf").write_bytes(b"weights")

    row = profile_model(
        "14B",
        base_root=tmp_path,
        explicit_root=None,
        artifact_roots=[],
        endpoint_profiles=[],
        endpoint_gate_rows=[],
        max_entries=50,
    )

    assert row["root"] == str(root)
    assert row["root_exists"] is True


def test_build_report_attaches_endpoint_profile_artifacts(tmp_path):
    root = tmp_path / "models" / "Qwen2.5-Coder-14B-Instruct"
    root.mkdir(parents=True)
    (root / "model.gguf").write_bytes(b"weights")
    endpoint_profiles = tmp_path / "model_endpoint_profiles.json"
    endpoint_gate = tmp_path / "model_endpoint_gate.json"
    endpoint_profiles.write_text(
        '{"schema":"harness.model-endpoint-profiles/v1","profiles":[{"model":"14B","model_key":"14b","profile_id":"serve-14b","backend":"serve","provider_role":"flywheel","endpoint_url":"http://127.0.0.1:8765","agentic_backend":"harness.local_agent.ServeBackend","root_exists":true,"live_probed":false,"content_read":false}]}',
        encoding="utf-8",
    )
    endpoint_gate.write_text(
        '{"schema":"harness.model-endpoint-gate/v1","rows":[{"model":"14B","model_key":"14b","profile_id":"serve-14b","backend":"serve","provider_role":"flywheel","health_ok":true,"generation_ok":true,"failure_class":"","quality_score":1.0,"receipt_hash":"abcdef1234567890"}]}',
        encoding="utf-8",
    )

    report = build_report(
        models=["14B"],
        base_root=tmp_path,
        explicit_roots={},
        artifact_roots=[],
        endpoint_profile_artifacts=[endpoint_profiles],
        endpoint_gate_artifacts=[endpoint_gate],
        max_entries=20,
    )

    row = report["models"][0]
    assert row["endpoint_profile_count"] == 1
    assert row["endpoint_profiles"][0]["profile_id"] == "serve-14b"
    assert row["endpoint_gate_row_count"] == 1
    assert row["endpoint_gate_generation_ok_count"] == 1
    assert report["summary"]["endpoint_profile_matches"] == 1
    assert report["summary"]["endpoint_gate_generation_ok"] == 1


def test_build_report_marks_missing_models_as_missing(tmp_path):
    report = build_report(
        models=["14B", "32B"],
        base_root=tmp_path,
        explicit_roots={},
        artifact_roots=[],
        endpoint_profile_artifacts=[],
        endpoint_gate_artifacts=[],
        max_entries=20,
    )

    assert report["schema"] == "harness.model-release-readiness/v1"
    assert report["summary"]["models"] == 2
    assert report["summary"]["missing_models"] == 2
    assert report["summary"]["release_ready_models"] == 0
