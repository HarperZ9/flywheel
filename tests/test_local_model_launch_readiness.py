import json

from scripts.run_local_model_launch_readiness import build_report, split_csv


def test_split_csv_skips_empty_values():
    assert split_csv("14B,, 32B") == ["14B", "32B"]


def _write_profiles(path):
    path.write_text(json.dumps({
        "schema": "harness.model-endpoint-profiles/v1",
        "profiles": [
            {
                "profile_id": "serve-14b",
                "model": "14B",
                "model_key": "14b",
                "backend": "serve",
                "provider_role": "flywheel",
                "endpoint_url": "http://127.0.0.1:8765",
                "model_ref": "serve:14b",
                "model_root": "C:/models/14b",
                "root_exists": True,
                "launch_command_template": "python harness/serve.py --model-profile 14b --port 8765",
            },
            {
                "profile_id": "serve-32b",
                "model": "32B",
                "model_key": "32b",
                "backend": "serve",
                "provider_role": "flywheel",
                "endpoint_url": "http://127.0.0.1:8767",
                "model_ref": "serve:32b",
                "model_root": "C:/models/32b",
                "root_exists": True,
                "launch_command_template": "python harness/serve.py --model-profile 32b --port 8767",
            },
        ],
    }), encoding="utf-8")


def test_launch_readiness_marks_free_serve_port_ready(tmp_path):
    profiles = tmp_path / "profiles.json"
    _write_profiles(profiles)

    report = build_report(
        profile_artifact=str(profiles),
        models=["32B"],
        backends=["serve"],
        owner_lookup=lambda host, port: [],
        port_probe=lambda host, port, timeout: False,
    )

    row = report["rows"][0]
    assert row["readiness"] == "ready_to_launch"
    assert row["can_launch_without_displacing"] is True
    assert report["summary"]["ready_to_launch_rows"] == 1
    assert report["summary"]["blocking_rows"] == 0


def test_launch_readiness_detects_wrong_service_port_conflict(tmp_path):
    profiles = tmp_path / "profiles.json"
    _write_profiles(profiles)

    report = build_report(
        profile_artifact=str(profiles),
        models=["32B"],
        backends=["serve"],
        owner_lookup=lambda host, port: [{
            "pid": 123,
            "process_name": "python.exe",
            "command_line": "python -m http.server 8767",
        }],
        port_probe=lambda host, port, timeout: True,
    )

    row = report["rows"][0]
    assert row["readiness"] == "port_conflict_wrong_service"
    assert row["owner_kind"] == "generic_http_server"
    assert row["can_launch_without_displacing"] is False
    assert report["summary"]["port_conflict_rows"] == 1
    assert report["summary"]["blocking_rows"] == 1


def test_launch_readiness_marks_harness_serve_as_candidate_running(tmp_path):
    profiles = tmp_path / "profiles.json"
    _write_profiles(profiles)

    report = build_report(
        profile_artifact=str(profiles),
        models=["14B"],
        backends=["serve"],
        owner_lookup=lambda host, port: [{
            "pid": 456,
            "process_name": "python.exe",
            "command_line": "python C:/dev/local-model/harness/serve.py --model-profile 14b",
        }],
        port_probe=lambda host, port, timeout: True,
    )

    row = report["rows"][0]
    assert row["readiness"] == "candidate_running_gate_required"
    assert row["owner_kind"] == "harness_serve"
    assert report["summary"]["candidate_running_rows"] == 1
    assert report["summary"]["blocking_rows"] == 0
