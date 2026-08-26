import hashlib
import json

import pytest

from harness.model_profiles import (MODEL_PROFILES, RELEASE_IDENTITY_PROVENANCE,
                                    validate_release_identity_provenance)
from scripts.run_model_endpoint_profiles import build_report, split_names


def test_split_names_handles_empty_items():
    assert split_names("14B, 32B,,") == ["14B", "32B"]


def test_endpoint_profiles_cover_serve_and_ollama_without_probing(tmp_path):
    model_root = tmp_path / "models" / "Qwen2.5-Coder-14B-Instruct"
    model_root.mkdir(parents=True)

    report = build_report(
        models=["14B"],
        base_root=tmp_path,
        serve_url="http://127.0.0.1:8765",
        ollama_url="http://127.0.0.1:11434",
    )

    assert report["schema"] == "harness.model-endpoint-profiles/v1"
    assert report["summary"]["profiles"] == 3
    assert report["summary"]["existing_roots"] == 2
    assert report["summary"]["live_probed"] is False
    profile_ids = [row["profile_id"] for row in report["profiles"]]
    assert profile_ids == ["serve-14b", "ollama-14b", "ollama-release-14b"]
    serve = [row for row in report["profiles"] if row["profile_id"] == "serve-14b"][0]
    ollama = [row for row in report["profiles"] if row["profile_id"] == "ollama-14b"][0]
    assert serve["provider_role"] == "flywheel"
    assert serve["model_root"] == str(model_root)
    assert serve["health_url"].endswith("/health")
    assert ollama["provider_role"] == "ollama_local"
    assert ollama["generate_url"].endswith("/api/chat")
    assert "SERVE_MODEL_PATH" in serve["env_presence"]


def test_endpoint_profiles_default_to_separate_serve_urls_for_14b_and_32b(tmp_path):
    (tmp_path / "models" / "Qwen2.5-Coder-14B-Instruct").mkdir(parents=True)
    (tmp_path / "models" / "Qwen2.5-Coder-32B-Instruct").mkdir(parents=True)

    report = build_report(
        models=["14B", "32B"],
        base_root=tmp_path,
        serve_url="",
        ollama_url="http://127.0.0.1:11434",
    )

    serve = {
        row["model"]: row
        for row in report["profiles"]
        if row["backend"] == "serve"
    }
    assert serve["14B"]["endpoint_url"] == "http://127.0.0.1:8765"
    assert serve["32B"]["endpoint_url"] == "http://127.0.0.1:8767"
    assert serve["32B"]["model_ref"] == "Qwen2.5-Coder-32B-Instruct (base, nf4)"
    assert "--model-profile 32b" in serve["32B"]["launch_command_template"]
    assert "SERVE_PORT=8767" in serve["32B"]["launch_command_template"]


def test_endpoint_profiles_include_32b_cpu_offload_runtime(tmp_path):
    (tmp_path / "models" / "Qwen2.5-Coder-32B-Instruct").mkdir(parents=True)

    report = build_report(
        models=["32B"],
        base_root=tmp_path,
        serve_url="",
        serve_urls={"32b": "http://127.0.0.1:8768"},
        runtime_strategies={"32b": "cpu-offload"},
        ollama_url="http://127.0.0.1:11434",
    )

    serve = [row for row in report["profiles"] if row["backend"] == "serve"][0]
    assert serve["endpoint_url"] == "http://127.0.0.1:8768"
    assert serve["runtime"]["strategy"] == "cpu-offload"
    assert serve["runtime"]["requires_offload"] is True
    assert "--device-map" in serve["serve_args"]
    assert "auto" in serve["serve_args"]
    assert "--offload-folder" in serve["serve_args"]
    assert "--max-memory-gpu" in serve["launch_command_template"]


def _release_row(report):
    return [row for row in report["profiles"] if row["profile_id"] == "ollama-release-14b"][0]


def test_release_ollama_profile_root_exists_tracks_trained_artifact_presence(tmp_path):
    (tmp_path / "models" / "Qwen2.5-Coder-14B-Instruct").mkdir(parents=True)
    (tmp_path / "models" / "Qwen2.5-Coder-32B-Instruct").mkdir(parents=True)
    kwargs = dict(
        models=["14B", "32B"],
        base_root=tmp_path,
        serve_url="",
        ollama_url="http://127.0.0.1:11434",
    )
    release_dir = tmp_path / "release" / "flywheel-local-coder-14b"

    no_release_dir = build_report(**kwargs)
    # Six, not five: serve + ollama + ollama-release for each of the two models.
    # The 32B gained a release profile when its CPT derivative shipped, and this
    # assertion said 5 and had been failing silently since then. Reporting a
    # release profile with root_exists False is more honest than omitting it,
    # which is what the second assertion here used to require.
    assert no_release_dir["summary"]["profiles"] == 6
    r32 = [row for row in no_release_dir["profiles"]
           if row["profile_id"] == "ollama-release-32b"]
    assert len(r32) == 1 and r32[0]["root_exists"] is False
    assert _release_row(no_release_dir)["root_exists"] is False

    release_dir.mkdir(parents=True)
    empty_release_dir = build_report(**kwargs)
    assert _release_row(empty_release_dir)["root_exists"] is False

    (release_dir / "telos-coder-14b-cpt2020-q4_k_m.gguf").write_bytes(b"gguf")
    with_artifact = build_report(**kwargs)
    release = _release_row(with_artifact)
    assert with_artifact["summary"]["profiles"] == 6
    assert release["root_exists"] is True
    assert release["backend"] == "ollama"
    assert release["model_ref"] == "ollama:flywheel-local-coder-14b"
    assert release["selectors"] == ["flywheel-local-coder-14b"]
    assert release["model_root"] == str(release_dir)
    assert release["release_artifact"] == "telos-coder-14b-cpt2020-q4_k_m.gguf"
    assert release["release_asset_sha256"] == "613db240e3efc6730f24042a4602d1f12f1c6b397af1d5a4d74f4e064d4064be"
    assert release["expected_ollama_digest"] == "sha256:7ff88ed3fd95eac7e79cb38a0a5ee3db39b7103a09d5a51d75fcda908522f6d8"
    assert release["launch_command_template"] == "ollama run flywheel-local-coder-14b"


def test_release_ollama_profile_binds_exact_32b_release_identity(tmp_path):
    (tmp_path / "models" / "Qwen2.5-Coder-32B-Instruct").mkdir(parents=True)
    report = build_report(models=["32B"], base_root=tmp_path, serve_url="", ollama_url="http://127.0.0.1:11434")
    release = next(row for row in report["profiles"] if row["profile_id"] == "ollama-release-32b")
    assert release["release_asset_sha256"] == "65e6133fbe4d12579a776047a71bebb98ab86f9e3d343ed821b51dac0ce312f4"
    assert release["expected_ollama_digest"] == "sha256:35fa696e662eb83293491d4b87de1d1308254d82be7aa8244f4fa442bf0e09d9"


def test_release_digest_constants_match_public_safe_provenance_receipt():
    receipt = validate_release_identity_provenance()
    payload = {key: value for key, value in receipt.items() if key != "evidence_sha256"}
    evidence = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert RELEASE_IDENTITY_PROVENANCE.name == "ollama-manifest-digest-provenance-v1.json"
    assert receipt["schema"] == "harness.ollama-manifest-digest-provenance/v1"
    assert receipt["evidence_sha256"] == evidence
    rows = {row["native_model_name"]: row for row in receipt["models"]}
    for profile in MODEL_PROFILES.values():
        release = profile["release"]; row = rows[release["ollama_model_name"]]
        assert row["release_asset_sha256"] == release["artifact_sha256"]
        assert row["ollama_manifest_digest"] == release["ollama_manifest_digest"]


def test_release_digest_provenance_rejects_tampered_evidence(tmp_path):
    receipt = json.loads(RELEASE_IDENTITY_PROVENANCE.read_text(encoding="utf-8"))
    receipt["models"][0]["ollama_manifest_digest"] = "sha256:" + "0" * 64
    tampered = tmp_path / "tampered.json"; tampered.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        validate_release_identity_provenance(tampered)
