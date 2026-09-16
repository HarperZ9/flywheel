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


def test_canon_payload_pins_context_source_without_expanding_public_tools():
    rows = [json.loads(line) for line in Path(
        "packaging/python-lane-payloads.jsonl"
    ).read_text(encoding="utf-8").splitlines() if line]
    canon = next(row for row in rows if row["lane"] == "canon")

    assert canon["owner_commit"] == "ba13fc3fc7582fbc1ae1a720e5cd86ea124d7675"
    assert canon["component_descriptor"]["source"]["commit"] == canon["owner_commit"]
    assert canon["component_descriptor"]["entrypoint"]["module"] == "canon.local_mcp"
    assert canon["component_descriptor"]["allowed_tools"] == [
        "canon.status", "canon.doctor"]
    assert canon["mcp"]["static_tool_names"] == [
        "canon.status", "canon.doctor", "canon.blocks",
        "canon.render", "canon.validate", "canon.check"]
    for module in ("canon.context_mcp", "canon.context_store",
                   "canon.context_query", "canon.context_records"):
        assert module in canon["hidden_imports"]
    assert canon["owner_project"]["license_files"] == [{
        "bytes": 4216,
        "path": "LICENSE",
        "sha256": "sha256:5d4abfef8a42cb0b1762662ae9745b01cd729991e60c2fee83d6ea8ee752cb6d",
    }]
