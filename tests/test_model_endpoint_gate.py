import json

from harness.local_agent import OllamaBackend, ServeBackend
from scripts.run_model_endpoint_gate import _backend_for_profile, build_report, main


def test_backend_for_profile_uses_backend_defaults_without_injected_transport():
    serve = _backend_for_profile(
        {"backend": "serve", "endpoint_url": "http://127.0.0.1:8765"},
        timeout_seconds=12.0,
    )
    ollama = _backend_for_profile(
        {
            "backend": "ollama",
            "endpoint_url": "http://127.0.0.1:11434",
            "selectors": ["qwen2.5-coder:14b"],
        },
        timeout_seconds=12.0,
    )

    assert isinstance(serve, ServeBackend)
    assert callable(serve.transport)
    assert serve.timeout == 12.0
    assert isinstance(ollama, OllamaBackend)
    assert callable(ollama.transport)
    assert ollama.model == "qwen2.5-coder:14b"


def fake_transport(method, url, body, timeout):
    if url.endswith("/health"):
        return 200, {"ok": True}
    if url.endswith("/generate"):
        return 200, {"text": "local endpoint gate active", "model_ref": "serve:test", "seed": 0}
    if url.endswith("/api/tags"):
        return 200, {"models": [{"name": "qwen2.5-coder:14b"}]}
    if url.endswith("/api/chat"):
        return 200, {"message": {"content": "ollama endpoint gate active"}}
    return 404, {"error": "not found"}


def test_model_endpoint_gate_probes_profile_rows_with_injected_transport(tmp_path):
    profiles = tmp_path / "profiles.json"
    profiles.write_text(json.dumps({
        "schema": "harness.model-endpoint-profiles/v1",
        "profiles": [
            {
                "profile_id": "serve-14b",
                "model": "14B",
                "model_key": "14b",
                "backend": "serve",
                "provider_role": "flywheel",
                "endpoint_url": "http://127.0.0.1:8765",
            },
            {
                "profile_id": "ollama-14b",
                "model": "14B",
                "model_key": "14b",
                "backend": "ollama",
                "provider_role": "ollama_local",
                "endpoint_url": "http://127.0.0.1:11434",
                "selectors": ["qwen2.5-coder:14b"],
            },
        ],
    }), encoding="utf-8")

    report = build_report(
        profile_artifact=str(profiles),
        models=["14B"],
        backends=[],
        transport=fake_transport,
    )

    assert report["schema"] == "harness.model-endpoint-gate/v1"
    assert report["summary"]["profiles_selected"] == 2
    assert report["summary"]["health_ok_rows"] == 2
    assert report["summary"]["generation_ok_rows"] == 2
    assert report["summary"]["failed_rows"] == 0
    assert {row["provider_role"] for row in report["rows"]} == {"flywheel", "ollama_local"}
    assert all(row["response_sha256"] for row in report["rows"])
    assert all(row["quality_score"] == 1.0 for row in report["rows"])
    assert all(row["receipt_hash"] for row in report["rows"])


def test_endpoint_gate_main_folds_unavailable_endpoints_without_strict_exit(tmp_path):
    profiles = tmp_path / "profiles.json"
    out = tmp_path / "gate.json"
    profiles.write_text(json.dumps({
        "schema": "harness.model-endpoint-profiles/v1",
        "profiles": [
            {
                "profile_id": "serve-14b",
                "model": "14B",
                "model_key": "14b",
                "backend": "unsupported",
                "provider_role": "flywheel",
                "endpoint_url": "http://127.0.0.1:8765",
            }
        ],
    }), encoding="utf-8")

    rc = main([
        "--profile-artifact",
        str(profiles),
        "--out",
        str(out),
    ])

    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["summary"]["failed_rows"] == 1
    assert report["rows"][0]["quality_score"] == 0.0
    assert report["rows"][0]["receipt_hash"]


def test_endpoint_gate_main_can_fail_strictly_for_release_gates(tmp_path):
    profiles = tmp_path / "profiles.json"
    profiles.write_text(json.dumps({
        "schema": "harness.model-endpoint-profiles/v1",
        "profiles": [
            {
                "profile_id": "serve-14b",
                "model": "14B",
                "model_key": "14b",
                "backend": "unsupported",
                "provider_role": "flywheel",
                "endpoint_url": "http://127.0.0.1:8765",
            }
        ],
    }), encoding="utf-8")

    rc = main([
        "--profile-artifact",
        str(profiles),
        "--strict-exit",
    ])

    assert rc == 1
