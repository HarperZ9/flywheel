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
    assert report["async_lanes"] == ["forum"]
    # The registry caught up with index 2.13.0 and forum 1.14.0, so no row
    # is ahead of it.
    assert report["registry_updates"] == []


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

    assert canon["owner_commit"] == "7bbd7ad0a565dba81ad16812e4070930a3cd3ae5"
    assert canon["component_descriptor"]["source"]["commit"] == canon["owner_commit"]
    assert canon["component_descriptor"]["entrypoint"]["module"] == "canon.local_mcp"
    # Admission follows the lane tool policy: T1 tools only, so canon.render
    # (T2 in the reviewed draft) stays out.
    assert canon["component_descriptor"]["allowed_tools"] == [
        "canon.status", "canon.doctor", "canon.blocks", "canon.validate", "canon.check"]
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
    # index 2.15.0 (tag v2.15.0) holds the bounded context envelope and index.route
    assert index["owner_commit"] == "b2e4dcefff9d9d9a339e23d64c58bb4a5149ef92"
    assert index["component_descriptor"]["source"]["commit"] == index["owner_commit"]
    for module in ("index_graph.context.envelope", "index_graph.route"):
        assert module in index["hidden_imports"]
    for path in ("src/index_graph/context/envelope.py", "src/index_graph/route.py"):
        assert any(
            item["path"] == path
            for item in index["component_descriptor"]["source"]["files"]
        ), path

    plexus = by_lane["plexus"]
    assert plexus["owner_commit"] == "825b992c51e9eac749c046e9c896c251d37017a7"
    assert plexus["component_descriptor"]["source"]["commit"] == plexus["owner_commit"]
    assert "plexus.registry" in plexus["hidden_imports"]
    assert any(
        item["path"] == "src/plexus/registry.py"
        for item in plexus["component_descriptor"]["source"]["files"]
    )


def test_runtime_dependency_must_be_staged_by_the_studio_runtime(tmp_path):
    source = Path("packaging/python-lane-payloads.jsonl")
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line]
    surface = next(row for row in rows if row["lane"] == "accountable-surface")
    assert surface["owner_project"]["runtime_dependencies"] == [
        "coherence-membrane>=0.1.0", "proof-surface>=0.1.0"]
    surface["owner_project"]["runtime_dependencies"].append("requests>=2")
    tampered = tmp_path / "payloads.jsonl"
    tampered.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/check_python_lane_payload_manifest.py", str(tampered)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "not staged by the Studio runtime" in result.stdout
    assert "requests>=2" in result.stdout
