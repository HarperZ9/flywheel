import importlib.util
import json
import os
import subprocess
import sys
from argparse import Namespace
from hashlib import sha256
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# The production manifest binds each lane to a vendored source tree that is
# staged outside the repository. Real-source integration requires an explicit
# FLYWHEEL_PYTHON_LANE_SOURCE_ROOT; a configured but incomplete tree must fail.
# Synthetic-source coverage runs everywhere. A skip does not qualify a release.
SOURCE_ROOT = os.environ.get("FLYWHEEL_PYTHON_LANE_SOURCE_ROOT", "")
_SOURCES_CONFIGURED = "FLYWHEEL_PYTHON_LANE_SOURCE_ROOT" in os.environ


def _run(*args):
    return subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_python_lane_payloads",
        REPO / "scripts" / "build_python_lane_payloads.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("configured", [False, True])
def test_production_source_integration_requires_explicit_opt_in(tmp_path, configured):
    env = os.environ.copy()
    env.pop("FLYWHEEL_PYTHON_LANE_SOURCE_ROOT", None)
    if configured:
        env["FLYWHEEL_PYTHON_LANE_SOURCE_ROOT"] = str(tmp_path / "missing-source")
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_python_lane_payload_build.py::"
         "test_python_lane_payload_builder_writes_source_closure_manifest",
         "-o", "addopts=", "-q", "-ra"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == (1 if configured else 0), result.stdout + result.stderr
    assert ("1 failed" if configured else "1 skipped") in result.stdout


def test_python_lane_payload_builder_rejects_c_drive_sources(tmp_path):
    manifest = tmp_path / "payloads.jsonl"
    row = json.loads((REPO / "packaging" / "python-lane-payloads.jsonl").read_text(encoding="utf-8").splitlines()[0])
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


@pytest.mark.parametrize("source_state", ["complete", "missing", "hash-mismatch"])
def test_python_lane_payload_builder_validates_synthetic_source_closure(tmp_path, monkeypatch, source_state):
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
    args = Namespace(
        manifest=str(manifest),
        source_root=str(tmp_path / "sources"),
        out=str(out),
        builder_python=sys.executable,
        skip_wheel_build=True,
    )
    if source_state != "complete":
        source_file = source_dir / "src" / "gather" / "__init__.py"
        if source_state == "missing":
            source_file.unlink()
        else:
            source_file.write_bytes(b"VERSION = \"9.9.9\"\n")
        expected = "missing source file" if source_state == "missing" else "hash mismatch"
        with pytest.raises(builder.PayloadBuildError, match=expected):
            builder.build_payloads(args)
        assert not (out / "python-lane-payload-build-manifest.json").exists()
        return
    receipt = builder.build_payloads(args)

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


def test_python_lane_payload_builder_names_a_fixture_for_every_manifest_row():
    # The receipt copies FIXTURES[lane] for each manifest row, so a row with no
    # entry crashes the build with a KeyError. The source-backed test below runs
    # only where the vendored sources are staged, so this check runs everywhere.
    # Each fixture tool must be one the row admits, or the receipt names a
    # workflow the bundled lane cannot serve.
    builder = _load_builder()
    rows = [json.loads(line) for line in (REPO / "packaging" / "python-lane-payloads.jsonl")
            .read_text(encoding="utf-8").splitlines() if line.strip()]
    lanes = [row["lane"] for row in rows]
    assert sorted(builder.FIXTURES) == sorted(lanes)
    for row in rows:
        fixture = builder.FIXTURES[row["lane"]]
        assert fixture["tool"] and fixture["workflow"], row["lane"]
        admitted = set(row["component_descriptor"]["allowed_tools"])
        for tool in fixture["tool"].split("+"):
            assert tool in admitted, (row["lane"], tool)


@pytest.mark.skipif(
    not _SOURCES_CONFIGURED,
    reason="set FLYWHEEL_PYTHON_LANE_SOURCE_ROOT to opt into production-source "
           "integration; skipped integration does not qualify a release",
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
    manifest = (Path(__file__).resolve().parents[1] / "packaging"
                / "python-lane-payloads.jsonl").read_text(encoding="utf-8")
    # the lane list comes from the manifest, so a new payload row cannot leave
    # this test asserting an old count (C18)
    assert [row["lane"] for row in receipt["lanes"]] == [
        json.loads(line)["lane"] for line in manifest.splitlines() if line.strip()]
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
        REPO / "scripts" / "python_lane_fixture_netguard.py",
    )
    assert spec and spec.loader
    guard_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard_module)

    guard = guard_module.create_network_guard(tmp_path)
    proof = guard_module.prove_network_guard(sys.executable, Path(guard["path"]), tmp_path)

    assert proof["enforced"] is True
    assert "network disabled by flywheel python lane fixture" in proof["probe"]["blocked"]
