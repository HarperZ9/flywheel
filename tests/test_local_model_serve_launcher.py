import json

from scripts.run_local_model_serve_launcher import build_report, split_csv


def test_split_csv_ignores_empty_items():
    assert split_csv("32B,,14B") == ["32B", "14B"]


def test_serve_launcher_builds_plan_without_starting(tmp_path):
    profiles = tmp_path / "profiles.json"
    profiles.write_text(json.dumps({
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
                "aliases": ["32b", "qwen2.5-coder-32b"],
            }
        ],
    }), encoding="utf-8")

    report = build_report(
        profile_artifact=str(profiles),
        models=["32B"],
        serve_python="python",
        start=False,
    )

    row = report["rows"][0]
    assert report["summary"]["planned_rows"] == 1
    assert report["summary"]["started_rows"] == 0
    assert row["command"][-2:] == ["--port", "8768"]
    assert "--model-profile" in row["command"]
    assert "32b" in row["command"]
    assert row["failure_class"] == ""


def test_serve_launcher_marks_missing_root_without_starting(tmp_path):
    profiles = tmp_path / "profiles.json"
    profiles.write_text(json.dumps({
        "schema": "harness.model-endpoint-profiles/v1",
        "profiles": [
            {
                "profile_id": "serve-32b",
                "model": "32B",
                "model_key": "32b",
                "backend": "serve",
                "endpoint_url": "http://127.0.0.1:8768",
                "model_ref": "ref",
                "model_root": "missing",
                "root_exists": False,
            }
        ],
    }), encoding="utf-8")

    report = build_report(
        profile_artifact=str(profiles),
        models=["32B"],
        serve_python="python",
        start=False,
    )

    assert report["rows"][0]["failure_class"] == "model_root_missing"
    assert report["summary"]["failed_rows"] == 1
