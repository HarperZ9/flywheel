import json

from scripts.run_local_model_serve_launcher import _classify_start_failure, build_report, split_csv


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
                "serve_args": ["--device-map", "auto", "--max-memory-gpu", "20GiB"],
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
    assert "--device-map" in row["command"]
    assert "20GiB" in row["command"]
    assert row["failure_class"] == ""
    assert row["terminate_on_timeout"] is False
    assert row["terminated_on_timeout"] is False


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


def test_serve_launcher_classifies_missing_torch_from_log(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text("ModuleNotFoundError: No module named 'torch'\n", encoding="utf-8")

    assert _classify_start_failure("URLError", log) == "missing_dependency_torch"


def test_serve_launcher_classifies_weight_loading_timeout(tmp_path):
    log = tmp_path / "serve.log"
    log.write_text("Loading weights:  24%|##3       | 184/771 [01:10<05:34,  1.76it/s]\n", encoding="utf-8")

    assert _classify_start_failure("URLError", log) == "startup_timeout_loading_weights"
