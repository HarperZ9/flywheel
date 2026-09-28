import importlib.util
import json
import subprocess
import sys
from argparse import Namespace
from hashlib import sha256
from pathlib import Path


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "stage_python_lane_sources",
        Path("scripts/stage_python_lane_sources.py"),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_git(repo: Path, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _source_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "canon-src"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "Test")
    (repo / ".gitattributes").write_text("*.py text eol=lf\n", encoding="utf-8")
    data = b"VALUE = 'ba13 fixture'\n"
    path = repo / "src" / "canon" / "context_mcp.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    (repo / "LICENSE").write_text("MIT\n", encoding="utf-8")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "fixture")
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    return repo, commit


def _manifest(tmp_path: Path, commit: str, source_repo: Path) -> Path:
    data = b"VALUE = 'ba13 fixture'\n"
    row = {
        "lane": "canon",
        "owner_tag": "v0.1.0",
        "owner_commit": commit,
        "registry_source_repo": "public/canon",
        "component_descriptor": {"source": {
            "repo": str(source_repo),
            "files": [{"path": "src/canon/context_mcp.py",
                       "bytes": len(data),
                       "sha256": "sha256:" + sha256(data).hexdigest()}]}},
    }
    path = tmp_path / "manifest.jsonl"
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_stage_python_lane_sources_materializes_manifest_pinned_checkout(tmp_path):
    module = _load_module()
    source, commit = _source_repo(tmp_path)
    manifest = _manifest(tmp_path, commit, source)

    receipt = module.stage_sources(Namespace(
        manifest=str(manifest),
        source_root=str(tmp_path / "sources"),
        lane=["canon"],
        source_repo=[],
        receipt=str(tmp_path / "receipt.json"),
        bounded_receipt=str(tmp_path / "bounded.json"),
    ))

    staged = Path(receipt["lanes"][0]["path"])
    bounded = json.loads((tmp_path / "bounded.json").read_text())
    assert (staged / "src" / "canon" / "context_mcp.py").is_file()
    assert subprocess.check_output(
        ["git", "-C", str(staged), "rev-parse", "HEAD"], text=True).strip() == commit
    assert receipt["lanes"][0]["file_count"] == 1
    assert json.loads((tmp_path / "receipt.json").read_text())["verdict"] == "PASS"
    dumped = json.dumps(bounded)
    assert bounded["schema"] == "flywheel.python-lane-source-stage-bounded/v1"
    assert "source_root" not in bounded
    assert "path" not in dumped
    assert str(tmp_path).replace("\\", "/") not in dumped


def test_stage_python_lane_sources_refuses_dirty_existing_checkout(tmp_path):
    module = _load_module()
    source, commit = _source_repo(tmp_path)
    manifest = _manifest(tmp_path, commit, source)
    args = Namespace(manifest=str(manifest), source_root=str(tmp_path / "sources"),
                     lane=["canon"], source_repo=[], receipt=None,
                     bounded_receipt=None)
    module.stage_sources(args)
    staged = tmp_path / "sources" / "canon-v0.1.0"
    (staged / "src" / "canon" / "context_mcp.py").write_text("dirty\n")

    try:
        module.stage_sources(args)
    except module.StageError as exc:
        assert "source checkout is dirty" in str(exc)
    else:
        raise AssertionError("dirty staged checkout was accepted")


def test_stage_python_lane_sources_rejects_duplicate_rows(tmp_path):
    module = _load_module()
    source, commit = _source_repo(tmp_path)
    row_path = _manifest(tmp_path, commit, source)
    row = row_path.read_text(encoding="utf-8")
    manifest = tmp_path / "duplicate.jsonl"
    manifest.write_text(row + row, encoding="utf-8")

    try:
        module.stage_sources(Namespace(
            manifest=str(manifest), source_root=str(tmp_path / "sources"),
            lane=["canon"], source_repo=[], receipt=None,
            bounded_receipt=None))
    except module.StageError as exc:
        assert "duplicate lane row" in str(exc)
    else:
        raise AssertionError("duplicate manifest rows were accepted")


def test_stage_python_lane_sources_rejects_invalid_owner_commit(tmp_path):
    module = _load_module()
    source, commit = _source_repo(tmp_path)
    manifest = _manifest(tmp_path, commit, source)
    row = json.loads(manifest.read_text(encoding="utf-8"))
    row["owner_commit"] = "not-a-sha"
    manifest.write_text(json.dumps(row) + "\n", encoding="utf-8")

    try:
        module.stage_sources(Namespace(
            manifest=str(manifest), source_root=str(tmp_path / "sources"),
            lane=["canon"], source_repo=[], receipt=None,
            bounded_receipt=None))
    except module.StageError as exc:
        assert "owner_commit must be a 40-hex SHA" in str(exc)
    else:
        raise AssertionError("invalid owner commit was accepted")


def test_stage_python_lane_sources_default_root_is_repo_build_directory(monkeypatch):
    monkeypatch.delenv("FLYWHEEL_PYTHON_LANE_SOURCE_ROOT", raising=False)
    module = _load_module()

    assert module.DEFAULT_SOURCE_ROOT == module.ROOT / "build" / "python-lane-sources"


def test_stage_python_lane_sources_explicit_env_root_is_honored(monkeypatch, tmp_path):
    source_root = tmp_path / "explicit-source-root"
    monkeypatch.setenv("FLYWHEEL_PYTHON_LANE_SOURCE_ROOT", str(source_root))

    module = _load_module()

    assert module.DEFAULT_SOURCE_ROOT == source_root
