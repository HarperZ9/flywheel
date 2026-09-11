import importlib.util
import json
import os
import subprocess
import sys
from argparse import Namespace
from hashlib import sha256
from pathlib import Path

import pytest


# The production manifest binds each lane to a vendored source tree that is
# staged outside the repository (on the authoring machine, or wherever
# FLYWHEEL_PYTHON_LANE_SOURCE_ROOT points). Tests that need those real sources
# are gated on their presence; the build logic itself is covered on every runner
# by the synthetic-source test below.
SOURCE_ROOT = os.environ.get(
    "FLYWHEEL_PYTHON_LANE_SOURCE_ROOT",
    "D:/fw-ship-sweep-20260910/all-lanes-payloads/sources",
)
_SOURCES_PRESENT = Path(SOURCE_ROOT).is_dir()


def _run(*args):
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_python_lane_payloads",
        Path("scripts/build_python_lane_payloads.py"),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_lane_payload_builder_rejects_c_drive_sources(tmp_path):
    manifest = tmp_path / "payloads.jsonl"
    row = json.loads(Path("packaging/python-lane-payloads.jsonl").read_text(encoding="utf-8").splitlines()[0])
    row["local_source_root"] = "C:/dev/public/gather"
    manifest.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    result = _run(
        "scripts/build_python_lane_payloads.py",
        "--manifest", str(manifest),
        "--source-root", SOURCE_ROOT,
        "--out", str(tmp_path / "out"),
        "--skip-wheel-build",
    )

    assert result.returncode == 1
    assert "C: source roots are not allowed" in result.stdout


def test_python_lane_payload_builder_writes_source_closure_from_synthetic_sources(tmp_path, monkeypatch):
    # Exercise the closure build on a small synthetic tree so CI verifies source
    # hashing, notice copying, module counting and receipt shape without the
    # vendored production sources, whose exact content hashes cannot be faked.
    builder = _load_builder()
    # The C: source policy has its own dedicated test above. Neutralise it here
    # so this test does not depend on which drive the runner's temp dir is on.
    monkeypatch.setattr(builder, "_reject_c_source", lambda *a, **k: None)

    source_dir = tmp_path / "sources" / "gather-demo"
    (source_dir / "src" / "gather").mkdir(parents=True)
    contents = {
        "src/gather/__init__.py": b"VERSION = \"0.0.0\"\n",
        "src/gather/mcp.py": b"def serve():\n    return None\n",
        "src/gather/api.py": b"CONSTANT = 1\n",
    }
    files = []
    for rel, data in contents.items():
        path = source_dir / rel
        path.write_bytes(data)
        files.append({"path": rel, "sha256": "sha256:" + sha256(data).hexdigest(), "bytes": len(data)})
    license_data = b"MIT License\n"
    (source_dir / "LICENSE").write_bytes(license_data)

    descriptor = {
        "name": "gather",
        "schema": "flywheel.bundled-lane-component/v1",
        "source": {
            "algorithm": "sha256-canonical-source-manifest/v1",
            "file_count": len(files),
            "files": files,
        },
    }
    row = {
        "lane": "gather",
        "owner_tag": "demo",
        "owner_commit": "0" * 40,
        "hidden_imports": ["gather.mcp"],
        "component_descriptor": descriptor,
        "component_descriptor_sha256": "sha256:" + builder.canonical_sha256(descriptor),
        "owner_project": {
            "name": "gather",
            "version": "0.0.0",
            "license_files": [
                {"path": "LICENSE", "sha256": "sha256:" + sha256(license_data).hexdigest()},
            ],
        },
    }
    manifest = tmp_path / "synthetic.jsonl"
    manifest.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")

    out = tmp_path / "out"
    receipt = builder.build_payloads(Namespace(
        manifest=str(manifest),
        source_root=str(tmp_path / "sources"),
        out=str(out),
        builder_python=sys.executable,
        skip_wheel_build=True,
    ))

    assert receipt["schema"] == "flywheel.python-lane-payload-build-manifest/v1"
    assert receipt["verdict"] == "PASS"
    assert receipt["wheel_build"]["skipped"] is True
    assert [lane["lane"] for lane in receipt["lanes"]] == ["gather"]
    lane = receipt["lanes"][0]
    assert lane["source_closure_sha256"].startswith("sha256:")
    assert lane["module_file_count"] == 3
    assert lane["source_bytes"] == sum(len(data) for data in contents.values())
    assert lane["notice_files"]
    assert lane["notice_files"][0]["source_path"] == "LICENSE"
    assert lane["fixture"]["tool"] == "gather.docs"
    written = json.loads((out / "python-lane-payload-build-manifest.json").read_text(encoding="utf-8"))
    assert written["verdict"] == "PASS"


@pytest.mark.skipif(
    not _SOURCES_PRESENT,
    reason="production vendored sources are staged only where "
           "FLYWHEEL_PYTHON_LANE_SOURCE_ROOT points (the authoring machine)",
)
def test_python_lane_payload_builder_writes_source_closure_manifest(tmp_path):
    out = tmp_path / "payload-out"
    result = _run(
        "scripts/build_python_lane_payloads.py",
        "--source-root", SOURCE_ROOT,
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
    assert all(row["network"] == "blocked" for row in payload["fixtures"])
    assert payload["fixtures"][0]["tool"] == "gather.docs"


def test_python_lane_network_guard_blocks_socket(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "python_lane_fixture_netguard",
        Path("scripts/python_lane_fixture_netguard.py"),
    )
    assert spec and spec.loader
    guard_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard_module)

    guard = guard_module.create_network_guard(tmp_path)
    proof = guard_module.prove_network_guard(sys.executable, Path(guard["path"]), tmp_path)

    assert proof["enforced"] is True
    assert "network disabled by flywheel python lane fixture" in proof["probe"]["blocked"]
