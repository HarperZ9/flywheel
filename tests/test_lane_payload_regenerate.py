"""The committed lane payload rows are exactly what the generator produces.

Every row in ``packaging/python-lane-payloads.jsonl`` is regenerated from its
pinned revision and compared byte for byte. The generator runs in a child with
``-S``, so no installed copy of a lane or of its dependencies can stand in for
the pinned source: accountable-surface must import its Studio dependencies from
the pinned Studio payload, and calibrate-pro must import its catalog slice with
no numpy present.

The regeneration cases need the lane source checkouts. They are gated on
``FLYWHEEL_LANE_CHECKOUT_ROOT`` (default ``C:/dev``, the authoring machine) and
skip per lane when the checkout or the pinned commit is absent. The row-shape
cases run everywhere.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging" / "python-lane-payloads.jsonl"
GENERATOR = ROOT / "scripts" / "generate_python_lane_payload_row.py"
CHECK = ROOT / "scripts" / "check_python_lane_payload_manifest.py"
CHECKOUT_ROOT = Path(os.environ.get("FLYWHEEL_LANE_CHECKOUT_ROOT", "C:/dev"))

LINES = [line for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.strip()]
ROWS = {json.loads(line)["lane"]: json.loads(line) for line in LINES}
FORUM_DATA_FILES = {
    "src/forum/manifests/default-roster.toml",
    "src/forum/skills/forum-route-preflight.sha256",
    "src/forum/skills/forum-route-preflight/SKILL.md",
    "src/forum/skills/forum-route-preflight/agents/openai.yaml",
    "src/forum/skills/forum-route-preflight/references/validation-cases.md",
}


def _row_line(lane: str) -> str:
    return next(line for line in LINES if json.loads(line)["lane"] == lane)


def _checkout_or_skip(lane: str) -> Path:
    sys.path.insert(0, str(ROOT))
    from harness.lanes_registry import LANES

    checkout = CHECKOUT_ROOT / LANES[lane].source_repo
    if not (checkout / ".git").exists():
        pytest.skip(f"no {lane} checkout under {CHECKOUT_ROOT}")
    commit = ROWS[lane]["owner_commit"]
    probe = subprocess.run(["git", "-C", str(checkout), "cat-file", "-e", f"{commit}^{{commit}}"],
                           capture_output=True, check=False)
    if probe.returncode != 0:
        pytest.skip(f"{lane} checkout lacks pinned commit {commit}")
    return checkout


def _run(*args: str, isolated: bool = True) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    flags = ["-S"] if isolated else []
    return subprocess.run([sys.executable, *flags, *args], capture_output=True,
                          check=False, cwd=ROOT, env=env, timeout=240)


@pytest.mark.timeout(240)
@pytest.mark.parametrize("lane", sorted(ROWS))
def test_row_regenerates_byte_for_byte_from_its_pin(lane):
    _checkout_or_skip(lane)
    result = _run(str(GENERATOR), lane, "--rev", ROWS[lane]["owner_commit"],
                  "--checkout-root", str(CHECKOUT_ROOT))
    out = result.stdout.decode("utf-8").strip()
    assert result.returncode == 0, out + result.stderr.decode("utf-8", "replace")
    assert out == _row_line(lane)


def test_manifest_holds_twelve_lanes_in_order():
    assert list(ROWS) == [
        "gather", "crucible", "index", "forum", "plexus", "mneme", "canon",
        "chorus", "relay", "accountable-surface", "articulate", "calibrate-pro"]


def test_forum_row_serves_mcp_surface_and_hashes_its_package_data():
    sys.path.insert(0, str(ROOT))
    from harness.lanes_registry import LANES

    forum = ROWS["forum"]
    assert LANES["forum"].bundled_mcp_module == "forum.mcp_surface"
    assert forum["mcp"]["module"] == "forum.mcp_surface"
    assert forum["mcp"]["callable"] == "serve_stdio"
    files = {item["path"]: item for item in forum["component_descriptor"]["source"]["files"]}
    data = {path for path in files if not path.endswith(".py")}
    assert data == FORUM_DATA_FILES
    assert sum(files[path]["bytes"] for path in data) == 18_917


def test_calibrate_pro_row_is_a_reviewed_catalog_slice():
    row = ROWS["calibrate-pro"]
    project = row["owner_project"]
    assert project["runtime_dependencies"] == []
    excluded = {item["requirement"]: item["reason"] for item in project["excluded_runtime_dependencies"]}
    assert set(excluded) == {"numpy>=1.24", "scipy>=1.10", "build-color>=1.0.0"}
    assert all(reason.strip() for reason in excluded.values())
    modules = set(row["payload_slice"]["modules"])
    assert row["mcp"]["module"] == "calibrate_pro.mcp" and "calibrate_pro.mcp" in modules
    assert set(row["hidden_imports"]) == modules
    paths = [item["path"] for item in row["component_descriptor"]["source"]["files"]]
    assert all(path.startswith("calibrate_pro/") and path.endswith(".py") for path in paths)
    assert not any(part in path for path in paths for part in ("/gui/", "/hardware/", "/core/"))
    assert row["owner_commit"] == "3d24d16d6b57b2264ac122b15a6b64530cefed26"
    assert row["owner_tag"] == "v2.0.0"


def test_articulate_row_pins_its_stdlib_mcp_server():
    row = ROWS["articulate"]
    assert row["owner_commit"] == "d7d5244db98c251fc7808f7a5eec4d5163c368a9"
    assert row["owner_tag"] == "v0.5.0"
    assert row["mcp"]["module"] == "articulate.local_mcp"
    assert {"judge", "fix", "polish", "score", "check"} <= set(row["mcp"]["static_tool_names"])
    assert row["owner_project"]["runtime_dependencies"] == []


def test_admitted_tools_come_from_the_policy():
    sys.path.insert(0, str(ROOT))
    from harness.lane_tool_policy import admitted_tools, validate_policy

    assert validate_policy() == []
    for lane, row in ROWS.items():
        admitted = admitted_tools(lane)
        assert {row["mcp"]["health_tool"], row["mcp"]["doctor_tool"]} <= set(admitted), lane
        assert row["component_descriptor"]["allowed_tools"] == admitted
        assert row["mcp"]["allowed_tools_for_initial_admission"] == admitted


def test_manifest_check_passes_on_the_committed_rows():
    result = _run(str(CHECK), isolated=False)
    report = json.loads(result.stdout.decode("utf-8"))
    assert result.returncode == 0, report
    assert report["lanes"] == list(ROWS)
    assert report["sliced_lanes"] == ["calibrate-pro"]


def _tampered_check(tmp_path, mutate) -> dict:
    rows = [json.loads(line) for line in LINES]
    mutate({row["lane"]: row for row in rows})
    path = tmp_path / "payloads.jsonl"
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
                    encoding="utf-8")
    result = _run(str(CHECK), str(path), isolated=False)
    assert result.returncode == 1
    return json.loads(result.stdout.decode("utf-8"))


def test_manifest_check_refuses_an_unreviewed_exclusion(tmp_path):
    def mutate(rows):
        rows["gather"]["owner_project"]["excluded_runtime_dependencies"] = [
            {"requirement": "numpy>=1", "reason": "self-declared"}]

    assert "excluded runtime dependencies differ from the reviewed slice" in (
        _tampered_check(tmp_path, mutate)["error"])


def test_manifest_check_refuses_numpy_back_in_the_slice(tmp_path):
    def mutate(rows):
        rows["calibrate-pro"]["owner_project"]["runtime_dependencies"] = ["numpy>=1.24"]

    assert "not staged by the Studio runtime" in _tampered_check(tmp_path, mutate)["error"]


def test_manifest_check_refuses_a_file_outside_the_slice(tmp_path):
    def mutate(rows):
        rows["calibrate-pro"]["payload_slice"]["modules"].append("calibrate_pro.gui")

    assert "payload slice differs from the reviewed slice" in (
        _tampered_check(tmp_path, mutate)["error"])


def test_forum_row_with_package_data_admits_at_runtime():
    sys.path.insert(0, str(ROOT))
    from harness import bundled_lane_descriptor as d

    for lane in ("forum", "articulate", "calibrate-pro"):
        row = ROWS[lane]
        assert d.validate_descriptor(
            lane, row["component_descriptor"], d.expected_from_manifest_row(row)) == ()
    assert d.manifest_file_row({"path": "src/forum/manifests/a.toml", "bytes": 1,
                                "sha256": "sha256:" + "0" * 64}, path_prefix="src/forum/")
    assert not d.manifest_file_row({"path": "src/forum/evil.pyd", "bytes": 1,
                                    "sha256": "sha256:" + "0" * 64}, path_prefix="src/forum/")
