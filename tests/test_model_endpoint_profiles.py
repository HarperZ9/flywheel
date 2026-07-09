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
