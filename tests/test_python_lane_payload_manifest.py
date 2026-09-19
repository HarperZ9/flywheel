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
    assert report["registry_updates"] == ["canon", "forum", "gather", "index", "mneme", "relay"]


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

    assert canon["owner_commit"] == "8c6a8228ce2117112c5dad74ddb0450ba80aa8ff"
    assert canon["component_descriptor"]["source"]["commit"] == canon["owner_commit"]
    assert canon["component_descriptor"]["entrypoint"]["module"] == "canon.local_mcp"
    assert canon["component_descriptor"]["allowed_tools"] == [
        "canon.status", "canon.doctor"]
    assert canon["mcp"]["static_tool_names"] == [
        "canon.status", "canon.doctor", "canon.blocks",
        "canon.render", "canon.validate", "canon.check"]
    for module in ("canon.context_mcp", "canon.context_store",
                   "canon.context_query", "canon.context_records",
                   "canon.context_related"):
        assert module in canon["hidden_imports"]
    assert canon["owner_project"]["license_files"] == [{
        "bytes": 4216,
        "path": "LICENSE",
        "sha256": "sha256:5d4abfef8a42cb0b1762662ae9745b01cd729991e60c2fee83d6ea8ee752cb6d",
    }]


def test_python_lane_payload_pins_accepted_index_and_plexus_sources():
    rows = [json.loads(line) for line in Path(
        "packaging/python-lane-payloads.jsonl"
    ).read_text(encoding="utf-8").splitlines() if line]
    by_lane = {row["lane"]: row for row in rows}

    index = by_lane["index"]
    assert index["owner_commit"] == "71c26eabde266b394370392816aaa74e1a55d88b"
    assert index["component_descriptor"]["source"]["commit"] == index["owner_commit"]
    assert "index_graph.context.envelope" in index["hidden_imports"]
    assert any(
        item["path"] == "src/index_graph/context/envelope.py"
        for item in index["component_descriptor"]["source"]["files"]
    )

    plexus = by_lane["plexus"]
    assert plexus["owner_commit"] == "f16aa20d52834db1a7beaaa44780200676caaf0b"
    assert plexus["component_descriptor"]["source"]["commit"] == plexus["owner_commit"]
    assert "plexus.registry" in plexus["hidden_imports"]
    assert any(
        item["path"] == "src/plexus/registry.py"
        for item in plexus["component_descriptor"]["source"]["files"]
    )
