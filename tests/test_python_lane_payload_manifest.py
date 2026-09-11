import json
import subprocess
import sys
from pathlib import Path


def test_python_lane_payload_manifest_check_passes():
    result = subprocess.run(
        [sys.executable, "scripts/check_python_lane_payload_manifest.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["verdict"] == "PASS"
    assert report["async_blockers"] == ["forum"]
    assert report["registry_updates"] == ["canon", "forum", "gather", "index", "mneme"]


def test_python_lane_payload_manifest_rejects_descriptor_tamper(tmp_path):
    source = Path("packaging/python-lane-payloads.jsonl")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
    rows[0]["component_descriptor_sha256"] = "sha256:" + "0" * 64
    tampered = tmp_path / "payloads.jsonl"
    tampered.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/check_python_lane_payload_manifest.py", str(tampered)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "descriptor digest mismatch" in result.stdout
