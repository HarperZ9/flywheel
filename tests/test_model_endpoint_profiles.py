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
    assert report["summary"]["profiles"] == 2
    assert report["summary"]["existing_roots"] == 2
    assert report["summary"]["live_probed"] is False
    serve = [row for row in report["profiles"] if row["backend"] == "serve"][0]
    ollama = [row for row in report["profiles"] if row["backend"] == "ollama"][0]
    assert serve["provider_role"] == "flywheel"
    assert serve["model_root"] == str(model_root)
    assert serve["health_url"].endswith("/health")
    assert ollama["provider_role"] == "ollama_local"
    assert ollama["generate_url"].endswith("/api/chat")
    assert "SERVE_MODEL_PATH" in serve["env_presence"]
