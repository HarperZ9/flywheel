import json

from scripts.run_local_model_resource_preflight import build_report, split_csv


def test_split_csv_skips_empty_items():
    assert split_csv("32B,, 14B") == ["32B", "14B"]


def _write_profiles(path):
    path.write_text(json.dumps({
        "schema": "harness.model-endpoint-profiles/v1",
        "profiles": [
            {
                "profile_id": "serve-32b",
                "model": "32B",
                "model_key": "32b",
                "backend": "serve",
                "endpoint_url": "http://127.0.0.1:8768",
                "model_ref": "Qwen2.5-Coder-32B-Instruct (base, nf4)",
                "model_root": "E:/local-model-run/models/Qwen2.5-Coder-32B-Instruct",
                "root_exists": True,
            }
        ],
    }), encoding="utf-8")


def test_resource_preflight_blocks_32b_when_free_vram_is_low(tmp_path):
    profiles = tmp_path / "profiles.json"
    _write_profiles(profiles)

    report = build_report(
        profile_artifact=str(profiles),
        models=["32B"],
        gpu_probe=lambda: [{
            "name": "RTX 4090",
            "memory_total_gb": 23.988,
            "memory_used_gb": 13.0,
            "memory_free_gb": 10.9,
            "utilization_gpu_pct": 10.0,
        }],
    )

    row = report["rows"][0]
    assert row["verdict"] in {"blocked_by_current_gpu_pressure", "requires_offload_or_smaller_runtime"}
    assert row["current_free_fits"] is False
    assert report["summary"]["blocking_rows"] == 1


def test_resource_preflight_records_gpu_unobserved(tmp_path):
    profiles = tmp_path / "profiles.json"
    _write_profiles(profiles)

    report = build_report(
        profile_artifact=str(profiles),
        models=["32B"],
        gpu_probe=lambda: [],
    )

    assert report["rows"][0]["verdict"] == "gpu_unobserved"
    assert report["summary"]["blocking_rows"] == 1
