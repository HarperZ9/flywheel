"""Freeze inputs beyond Python modules: slice trees, the slice check, Node lanes.

A reviewed slice (calibrate-pro) ships part of a package. The freeze must see
only the slice, so the stager copies the sliced files into their own tree and
the freeze reads that tree, never the full checkout. After the freeze, the
PYZ table of contents must hold exactly the slice modules of that package.
The Node-lane stage folder is a required freeze input: a build path that does
not stage it cannot freeze the gateway.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from argparse import Namespace
from hashlib import sha256
from pathlib import Path

import pytest

from harness.evidence_json import canonical_sha256
from scripts.frozen_payload_datas import (
    NODE_STAGE_DEST, NODE_STAGE_ENV, NODE_STAGE_RECEIPT, check_pyz_slices,
    node_lane_stage_datas)
from scripts.python_lane_freeze import python_lane_freeze_inputs
from scripts.stage_python_lane_sources import stage_sources

REPO = Path(__file__).resolve().parents[1]
FREEZE = re.compile(r"PyInstaller\W+packaging[\\/]flywheel-gateway\.spec")
NODE_STAGE = re.compile(r"scripts[\\/]stage_node_lanes\.py")
FREEZE_PATHS = (
    ".github/workflows/desktop-release.yml",
    "desktop/scripts/build_installer.ps1",
    "desktop/tool/run_ci_installed_acceptance.ps1",
)
SLICE_FILES = {
    "pkgslice/__init__.py": b"",
    "pkgslice/mcp.py": b"def serve():\n    from pkgslice import heavy\n    return heavy\n",
}
OUTSIDE_FILES = {
    "pkgslice/heavy.py": b"import numpy\n",
    "README.md": b"fixture\n",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _slice_repo(tmp_path: Path) -> Path:
    """A lane whose package sits at the repo root, pinned as a two-module slice."""
    origin = tmp_path / "origin"
    for rel, data in {**SLICE_FILES, **OUTSIDE_FILES}.items():
        (origin / rel).parent.mkdir(parents=True, exist_ok=True)
        (origin / rel).write_bytes(data)
    (origin / ".gitattributes").write_bytes(b"* -text\n")
    _git(origin, "init", "-q")
    _git(origin, "config", "user.email", "test@example.invalid")
    _git(origin, "config", "user.name", "Test")
    _git(origin, "add", ".")
    _git(origin, "commit", "-qm", "fixture")
    entries = [{"path": rel, "bytes": len(data), "sha256": "sha256:" + sha256(data).hexdigest()}
               for rel, data in sorted(SLICE_FILES.items())]
    row = {"lane": "slicelane", "owner_tag": "v1.0.0",
           "owner_commit": _git(origin, "rev-parse", "HEAD"),
           "registry_source_repo": "public/slicelane",
           "payload_slice": {"modules": ["pkgslice", "pkgslice.mcp"], "reason": "fixture"},
           "component_descriptor": {
               "entrypoint": {"module": "pkgslice.mcp"},
               "source": {"repo": str(origin), "path": "pkgslice", "files": entries,
                          "manifest_sha256": "sha256:" + canonical_sha256(entries)}}}
    repo = tmp_path / "repo"
    (repo / "packaging").mkdir(parents=True)
    (repo / "packaging" / "python-lane-payloads.jsonl").write_text(
        json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return repo


def _stage(repo: Path, source_root: Path) -> dict:
    return stage_sources(Namespace(
        manifest=str(repo / "packaging" / "python-lane-payloads.jsonl"),
        source_root=str(source_root), lane=None, all=True,
        source_repo=[], receipt=None, bounded_receipt=None))


@pytest.fixture
def isolated_imports(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    for name in [n for n in sys.modules if n.split(".")[0] == "pkgslice"]:
        del sys.modules[name]


def test_slice_stage_holds_only_the_slice_and_no_numpy_import(tmp_path, isolated_imports):
    repo = _slice_repo(tmp_path)
    source_root = tmp_path / "sources"
    _stage(repo, source_root)
    slice_src = source_root / "slicelane-v1.0.0-slice" / "src"
    staged = sorted(p.relative_to(slice_src).as_posix()
                    for p in slice_src.rglob("*") if p.is_file())
    assert staged == sorted(SLICE_FILES)
    for path in slice_src.rglob("*.py"):
        assert not re.search(rb"^\s*(import|from)\s+numpy", path.read_bytes(), re.M), path

    pathex, hidden, receipts = python_lane_freeze_inputs(repo, source_root, exclude=())
    assert pathex == [str(slice_src.resolve())]
    assert hidden == ["pkgslice", "pkgslice.mcp"]
    assert receipts[0]["module_count"] == 2


def test_slice_restage_rebuilds_its_tree_and_refuses_a_foreign_folder(tmp_path):
    repo = _slice_repo(tmp_path)
    source_root = tmp_path / "sources"
    _stage(repo, source_root)
    stray = source_root / "slicelane-v1.0.0-slice" / "src" / "pkgslice" / "stray.py"
    stray.write_bytes(b"import numpy\n")
    _stage(repo, source_root)
    assert not stray.exists()

    other = tmp_path / "other"
    foreign = other / "slicelane-v1.0.0-slice"
    foreign.mkdir(parents=True)
    (foreign / "keep.txt").write_bytes(b"not ours\n")
    with pytest.raises(RuntimeError, match="not a slice stage"):
        _stage(repo, other)
    assert (foreign / "keep.txt").exists()


def test_freeze_never_reads_the_full_checkout_of_a_sliced_lane(tmp_path, isolated_imports):
    repo = _slice_repo(tmp_path)
    source_root = tmp_path / "sources"
    _stage(repo, source_root)
    shutil.rmtree(source_root / "slicelane-v1.0.0-slice")
    with pytest.raises(RuntimeError, match="staged slicelane source missing"):
        python_lane_freeze_inputs(repo, source_root, exclude=())


def _toc(tmp_path: Path, names: list[str]) -> Path:
    path = tmp_path / "PYZ-00.toc"
    entries = [(name, f"C:\\x\\{name}.py", "PYMODULE") for name in names]
    path.write_text(repr((str(tmp_path / "PYZ-00.pyz"), entries)), encoding="utf-8")
    return path


def _slice_rows() -> list[dict]:
    return [{"lane": "slicelane", "payload_slice": {"modules": ["pkgslice", "pkgslice.mcp"]}},
            {"lane": "whole", "component_descriptor": {}}]


def test_pyz_check_passes_when_the_package_is_exactly_the_slice(tmp_path):
    toc = _toc(tmp_path, ["json", "pkgslice", "pkgslice.mcp", "pkgslicer"])
    receipts = check_pyz_slices(toc, _slice_rows())
    assert receipts == [{"lane": "slicelane", "modules": 2}]


@pytest.mark.parametrize("names,needle", [
    (["pkgslice", "pkgslice.mcp", "pkgslice.heavy"], "pkgslice.heavy"),
    (["pkgslice"], "pkgslice.mcp"),
    ([], "pkgslice"),
])
def test_pyz_check_refuses_extra_or_missing_slice_modules(tmp_path, names, needle):
    with pytest.raises(RuntimeError, match=re.escape(needle)):
        check_pyz_slices(_toc(tmp_path, names), _slice_rows())


def test_pyz_check_reads_the_calibrate_pro_slice_from_the_manifest(tmp_path):
    rows = [json.loads(line) for line in (REPO / "packaging" / "python-lane-payloads.jsonl")
            .read_text(encoding="utf-8").splitlines() if line.strip()]
    modules = next(r for r in rows if r["lane"] == "calibrate-pro")["payload_slice"]["modules"]
    assert check_pyz_slices(_toc(tmp_path, list(modules)), rows) == [
        {"lane": "calibrate-pro", "modules": len(modules)}]
    with pytest.raises(RuntimeError, match="calibrate_pro.targets"):
        check_pyz_slices(_toc(tmp_path, [*modules, "calibrate_pro.targets"]), rows)


def test_node_stage_is_required_and_must_carry_a_passing_receipt(tmp_path):
    with pytest.raises(RuntimeError, match=NODE_STAGE_ENV):
        node_lane_stage_datas(None)
    with pytest.raises(RuntimeError, match="missing"):
        node_lane_stage_datas(str(tmp_path / "absent"))
    stage = tmp_path / "node-lanes"
    stage.mkdir()
    with pytest.raises(RuntimeError, match=NODE_STAGE_RECEIPT):
        node_lane_stage_datas(str(stage))
    (stage / NODE_STAGE_RECEIPT).write_text('{"verdict": "FAIL"}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="PASS"):
        node_lane_stage_datas(str(stage))
    (stage / NODE_STAGE_RECEIPT).write_text('{"verdict": "PASS"}', encoding="utf-8")
    assert node_lane_stage_datas(str(stage)) == [(str(stage.resolve()), NODE_STAGE_DEST)]


@pytest.mark.parametrize("rel", FREEZE_PATHS)
def test_every_freeze_path_stages_node_lanes_before_the_freeze(rel):
    text = (REPO / rel).read_text(encoding="utf-8")
    freeze_at = FREEZE.search(text).start()
    stage = NODE_STAGE.search(text)
    assert stage and stage.start() < freeze_at, f"{rel} freezes without staging Node lanes"
    assert 0 <= text.find(NODE_STAGE_ENV) < freeze_at, f"{rel} never sets {NODE_STAGE_ENV}"


def test_installed_acceptance_requires_the_node_stager_in_the_target_commit():
    text = (REPO / "desktop/tool/run_ci_installed_acceptance.ps1").read_text(encoding="utf-8")
    required = text[text.index("function Assert-RequiredTargetFiles"):]
    required = required[:required.index("foreach")]
    assert '"scripts\\stage_node_lanes.py"' in required
