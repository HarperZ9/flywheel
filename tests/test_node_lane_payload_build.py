import json
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path


def _run(*args):
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_node_payload_builder_rejects_c_drive_telos_source(tmp_path):
    result = _run(
        "scripts/build_node_lane_payloads.py",
        "--out", str(tmp_path / "out"),
        "--cache", str(tmp_path / "cache"),
        "--telos-source-root", "C:/dev/public/telos",
        "--skip-downloads",
    )

    assert result.returncode == 1
    assert "C: source roots are not allowed" in result.stdout


def test_node_payload_archive_extraction_rejects_traversal(tmp_path):
    archive = tmp_path / "bad.tgz"
    with tarfile.open(archive, "w:gz") as tf:
        data = b"outside"
        info = tarfile.TarInfo("package/../outside.txt")
        info.size = len(data)
        tf.addfile(info, BytesIO(data))

    result = _run(
        "scripts/build_node_lane_payloads.py",
        "--extract-test-archive", str(archive),
        "--out", str(tmp_path / "out"),
        "--cache", str(tmp_path / "cache"),
        "--skip-downloads",
    )

    assert result.returncode == 1
    assert "unsafe archive path" in result.stdout


def test_node_lane_fixture_script_lists_bounded_workflows():
    result = _run("scripts/run_node_lane_payload_fixtures.py", "--list")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "flywheel.node-lane-fixtures/v1"
    assert [row["lane"] for row in payload["fixtures"]] == ["learn", "telos"]
    assert all(row["network"] == "none" for row in payload["fixtures"])
    assert payload["fixtures"][0]["status_tool"] == "learn_status"
    assert payload["fixtures"][1]["doctor_tool"] == "telos.doctor"
