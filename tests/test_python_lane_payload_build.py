import json
import subprocess
import sys
from pathlib import Path


def _run(*args):
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_python_lane_payload_builder_rejects_c_drive_sources(tmp_path):
    manifest = tmp_path / "payloads.jsonl"
    row = json.loads(Path("packaging/python-lane-payloads.jsonl").read_text(encoding="utf-8").splitlines()[0])
    row["local_source_root"] = "C:/dev/public/gather"
    manifest.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    result = _run(
        "scripts/build_python_lane_payloads.py",
        "--manifest", str(manifest),
        "--source-root", "D:/fw-ship-sweep-20260910/all-lanes-payloads/sources",
        "--out", str(tmp_path / "out"),
        "--skip-wheel-build",
    )

    assert result.returncode == 1
    assert "C: source roots are not allowed" in result.stdout


def test_python_lane_payload_builder_writes_source_closure_manifest(tmp_path):
    out = tmp_path / "payload-out"
    result = _run(
        "scripts/build_python_lane_payloads.py",
        "--source-root", "D:/fw-ship-sweep-20260910/all-lanes-payloads/sources",
        "--out", str(out),
        "--skip-wheel-build",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    receipt = json.loads((out / "python-lane-payload-build-manifest.json").read_text(encoding="utf-8"))
    assert receipt["schema"] == "flywheel.python-lane-payload-build-manifest/v1"
    assert receipt["wheel_build"]["skipped"] is True
    assert [row["lane"] for row in receipt["lanes"]] == [
        "gather", "crucible", "index", "forum", "plexus", "mneme", "canon"
    ]
    for row in receipt["lanes"]:
        assert row["source_closure_sha256"].startswith("sha256:")
        assert row["notice_files"]
        assert row["module_file_count"] > 0
        assert row["fixture"]["tool"]


def test_python_lane_fixture_script_lists_bounded_workflows():
    result = _run("scripts/run_python_lane_payload_fixtures.py", "--list")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "flywheel.python-lane-fixtures/v1"
    assert [row["lane"] for row in payload["fixtures"]] == [
        "gather", "crucible", "index", "forum", "plexus", "mneme", "canon"
    ]
    assert all(row["network"] == "none" for row in payload["fixtures"])
    assert payload["fixtures"][0]["tool"] == "gather.docs"
