from pathlib import Path

from scripts.run_model_release_readiness import GATE_FILES, build_report, profile_model, split_names


TRAINED_14B_ARTIFACT = "telos-coder-14b-cpt2020-q4_k_m.gguf"


def _profile(model, tmp_path):
    return profile_model(
        model,
        base_root=tmp_path,
        explicit_root=None,
        artifact_roots=[],
        endpoint_profiles=[],
        endpoint_gate_rows=[],
        max_entries=50,
    )


def _write_all_release_docs(root: Path) -> None:
    for names in GATE_FILES.values():
        for name in names:
            (root / name).write_text("doc", encoding="utf-8")


def test_split_names_handles_empty_items():
    assert split_names("14B, 32B,,") == ["14B", "32B"]


def test_profile_model_reports_static_release_gaps_without_reading_contents(tmp_path):
    root = tmp_path / "14B"
    root.mkdir()
    (root / TRAINED_14B_ARTIFACT).write_bytes(b"weights")
    (root / "MODEL_CARD.md").write_text("do-not-read", encoding="utf-8")
    (root / "README.md").write_text("do-not-read", encoding="utf-8")

    row = _profile("14B", tmp_path)

    assert row["model"] == "14B"
    assert row["root_exists"] is True
    assert row["content_read"] is False
    assert row["weight_file_count"] == 1
    assert row["trained"] is True
    assert row["trained_artifact_present"] is True
    assert row["enterprise_release_ready"] is False
    assert row["verdict"] == "MODEL_ARTIFACTS_WITH_RELEASE_GAPS"
    assert "checksums.sha256" in row["gates"]["integrity"]["missing_files"]
    assert "do-not-read" not in str(row)


def test_profile_model_32b_full_docs_and_weights_still_no_trained_artifact(tmp_path):
    root = tmp_path / "32B"
    root.mkdir()
    (root / "model-00001-of-00002.safetensors").write_bytes(b"weights")
    _write_all_release_docs(root)

    row = _profile("32B", tmp_path)

    assert row["root_exists"] is True
    assert row["weight_file_count"] == 1
    assert all(gate["missing"] == 0 for gate in row["gates"].values())
    assert row["trained"] is False
    assert row["trained_artifact_present"] is False
    assert row["verdict"] == "MODEL_NO_TRAINED_ARTIFACT"
    assert row["enterprise_release_ready"] is False
    assert "must not be republished" in row["release_identity"]["no_artifact_reason"]


def test_profile_model_trained_root_without_artifact_is_trained_artifact_missing(tmp_path):
    root = tmp_path / "14B"
    root.mkdir()
    (root / "model.gguf").write_bytes(b"weights")

    row = _profile("14B", tmp_path)

    assert row["root_exists"] is True
    assert row["weight_file_count"] == 1
    assert row["trained"] is True
    assert row["trained_artifact_present"] is False
    assert row["verdict"] == "MODEL_TRAINED_ARTIFACT_MISSING"
    assert row["release_identity"]["artifact_name"] == TRAINED_14B_ARTIFACT
    assert row["release_identity"]["public_name"] == "Flywheel-Local-Coder-14B"


def test_profile_model_prefers_release_root_over_base_model_root(tmp_path):
    base_dir = tmp_path / "models" / "Qwen2.5-Coder-14B-Instruct"
    base_dir.mkdir(parents=True)
    (base_dir / "model.gguf").write_bytes(b"base-weights")
    release_dir = tmp_path / "release" / "flywheel-local-coder-14b"
    release_dir.mkdir(parents=True)
    (release_dir / TRAINED_14B_ARTIFACT).write_bytes(b"gguf")

    row = _profile("14B", tmp_path)

    assert row["root"] == str(release_dir)
    assert row["candidate_roots"][0] == str(release_dir)
    assert row["trained_artifact_present"] is True


def test_profile_model_finds_known_qwen_model_directory_under_models(tmp_path):
    root = tmp_path / "models" / "Qwen2.5-Coder-14B-Instruct"
    root.mkdir(parents=True)
    (root / "model.gguf").write_bytes(b"weights")

    row = _profile("14B", tmp_path)

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
    assert report["summary"]["trained_models"] == 1
    assert report["summary"]["trained_artifacts_present"] == 0
