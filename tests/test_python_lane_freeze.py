import json
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from harness.evidence_json import canonical_sha256
from scripts.frozen_payload_datas import package_data_entries
from scripts.python_lane_freeze import (
    bundled_python_lanes, lane_hidden_imports, python_lane_freeze_datas,
    python_lane_freeze_inputs)

REPO = Path(__file__).resolve().parents[1]


def _row(files):
    return {"component_descriptor": {"source": {"files": files}}}


def test_lane_hidden_imports_derives_every_package_module():
    row = _row([
        {"path": "src/index_graph/__init__.py"},
        {"path": "src/index_graph/mcp.py"},
        {"path": "src/index_graph/arch/__init__.py"},
        {"path": "src/index_graph/arch/build.py"},
        {"path": "src/index_graph/data.json"},   # non-py is skipped
        {"path": "README.md"},                     # outside src is skipped
    ])
    assert lane_hidden_imports(row) == [
        "index_graph",
        "index_graph.arch",
        "index_graph.arch.build",
        "index_graph.mcp",
    ]


def test_lane_hidden_imports_is_sorted_and_deduped():
    row = _row([{"path": "src/pkg/a.py"}, {"path": "src/pkg/a.py"},
                {"path": "src/pkg/__init__.py"}])
    assert lane_hidden_imports(row) == ["pkg", "pkg.a"]


def test_bundled_python_lanes_excludes_only_relay_by_default():
    lanes = bundled_python_lanes(REPO)
    assert "relay" not in lanes
    # Canon is bundled through the helper too, so its bundled-lane entrypoint
    # (canon.local_mcp) reaches the freeze; only relay (the submodule) is out.
    assert lanes == ["accountable-surface", "articulate", "calibrate-pro", "canon",
                     "chorus", "crucible", "forum", "gather", "index", "mneme", "plexus"]


def test_bundled_python_lanes_exclusion_is_configurable():
    assert "canon" not in bundled_python_lanes(REPO, exclude=("relay", "canon"))


# --- Package data, slices and the import root (WP2) -------------------------


def _manifest_row(lane: str) -> dict:
    manifest = REPO / "packaging" / "python-lane-payloads.jsonl"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line)["lane"] == lane:
            return json.loads(line)
    raise AssertionError(f"no manifest row for {lane}")


def test_forum_default_roster_is_in_the_hash_and_in_the_datas():
    row = _manifest_row("forum")
    files = {item["path"]: item for item in row["component_descriptor"]["source"]["files"]}
    roster = "src/forum/manifests/default-roster.toml"
    # In the hash: the pinned source manifest names the file with its digest.
    assert files[roster]["sha256"].startswith("sha256:")
    assert row["component_descriptor"]["source"]["manifest_sha256"] == (
        "sha256:" + canonical_sha256(row["component_descriptor"]["source"]["files"]))
    # In the datas: it lands where importlib.resources.files("forum") looks.
    assert (roster, "forum/manifests") in package_data_entries(row)
    assert all(not rel.endswith(".py") for rel, _ in package_data_entries(row))


def test_hidden_imports_follow_a_package_at_the_repo_root():
    # calibrate-pro has no src/ directory; its package sits at the repo root.
    row = _manifest_row("calibrate-pro")
    assert lane_hidden_imports(row) == sorted(row["payload_slice"]["modules"])


def test_hidden_imports_skip_files_outside_the_package_path():
    row = {"component_descriptor": {"source": {"path": "pkg", "files": [
        {"path": "pkg/__init__.py"}, {"path": "pkg/mcp.py"},
        {"path": "setup.py"}, {"path": "tests/test_pkg.py"}]}}}
    assert lane_hidden_imports(row) == ["pkg", "pkg.mcp"]


def _entry(rel: str, data: bytes) -> dict:
    return {"path": rel, "bytes": len(data), "sha256": "sha256:" + sha256(data).hexdigest()}


def _data_lane(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A repo whose one lane ships a toml next to its modules, staged by hand."""
    files = {"src/lanefix_data/__init__.py": b"",
             "src/lanefix_data/mcp.py": b"def serve():\n    return 0\n",
             "src/lanefix_data/manifests/roster.toml": b"[roster]\nname = 'x'\n"}
    source_root = tmp_path / "sources"
    checkout = source_root / "datalane-v1.0.0"
    for rel, data in files.items():
        (checkout / rel).parent.mkdir(parents=True, exist_ok=True)
        (checkout / rel).write_bytes(data)
    entries = [_entry(rel, data) for rel, data in sorted(files.items())]
    row = {"lane": "datalane", "owner_tag": "v1.0.0", "owner_commit": "0" * 40,
           "component_descriptor": {
               "entrypoint": {"module": "lanefix_data.mcp"},
               "source": {"path": "src/lanefix_data", "files": entries,
                          "manifest_sha256": "sha256:" + canonical_sha256(entries)}}}
    repo = tmp_path / "repo"
    (repo / "packaging").mkdir(parents=True)
    (repo / "packaging" / "python-lane-payloads.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8")
    return repo, source_root, checkout


@pytest.fixture
def isolated_imports(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    for name in [n for n in sys.modules if n.split(".")[0] == "lanefix_data"]:
        del sys.modules[name]


def test_freeze_datas_carry_package_data_to_its_package_dir(tmp_path, isolated_imports):
    repo, source_root, checkout = _data_lane(tmp_path)
    datas = python_lane_freeze_datas(repo, source_root, exclude=())
    toml = (checkout / "src/lanefix_data/manifests/roster.toml").resolve()
    assert datas == [(str(toml), "lanefix_data/manifests")]
    pathex, hidden, _ = python_lane_freeze_inputs(repo, source_root, exclude=())
    assert pathex == [str((checkout / "src").resolve())]
    assert "lanefix_data.manifests" not in hidden


def test_freeze_datas_refuse_package_data_that_drifted_from_the_pin(
        tmp_path, isolated_imports):
    repo, source_root, checkout = _data_lane(tmp_path)
    (checkout / "src/lanefix_data/manifests/roster.toml").write_bytes(b"[roster]\n")
    with pytest.raises(RuntimeError, match="mismatch"):
        python_lane_freeze_datas(repo, source_root, exclude=())


def test_derived_hidden_imports_equal_each_rows_pinned_list():
    manifest = REPO / "packaging" / "python-lane-payloads.jsonl"
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == 12
    for row in rows:
        assert lane_hidden_imports(row) == sorted(row["hidden_imports"]), row["lane"]
