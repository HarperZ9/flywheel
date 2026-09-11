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


def test_node_lane_payload_manifest_check_passes():
    result = _run("scripts/check_node_lane_payload_manifest.py")

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["verdict"] == "PASS"
    assert report["lanes"] == ["learn", "telos"]
    assert report["runtime"]["version"] == "24.21.0"
    assert report["server_info"] == {
        "learn": {"name": "learn", "version": "1.6.0"},
        "telos": {"name": "project-telos-telos", "version": "0.3.0"},
    }


def test_node_lane_payload_manifest_rejects_descriptor_tamper(tmp_path):
    source = Path("packaging/node-lane-payloads.jsonl")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
    rows[0]["component_descriptor_sha256"] = "sha256:" + "0" * 64
    tampered = tmp_path / "node-lane-payloads.jsonl"
    tampered.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")

    result = _run("scripts/check_node_lane_payload_manifest.py", str(tampered))

    assert result.returncode == 1
    assert "descriptor digest mismatch" in result.stdout
