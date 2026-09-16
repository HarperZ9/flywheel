from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from scripts.studio_runtime_sources import (
    build_manifest_from_source_pins,
    checkout_source_pins,
    load_source_pins,
)


def _write(path: Path, text: str = "# fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pins_fixture(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    roots = {}
    for name, package in {
        "studio_engine": "studio_engine",
        "accountable_surface": "accountable_surface",
        "coherence_membrane": "coherence_membrane",
        "proof_surface": "proof_surface",
    }.items():
        root = tmp_path / name
        roots[name] = root
        src = root if name == "studio_engine" else root / "src"
        if name == "studio_engine":
            _write(root / "pyproject.toml", "[project]\nname = 'studio-engine'\n")
        _write(src / package / "__init__.py")
        _write(root / "LICENSE", name + " license\n")

    def section(name: str, rels: list[str], entries: list[str]) -> dict:
        src = roots[name] if name == "studio_engine" else roots[name] / "src"
        hashes = {rel: _sha(src / rel) for rel in rels}
        key = "required_file_hashes" if name == "studio_engine" else "file_hashes"
        files_key = "required_files" if name == "studio_engine" else "files"
        out = {"status": "ready", files_key: rels, key: hashes}
        if name != "studio_engine":
            out["entry_modules"] = entries
        return out

    doc = {
        "schema": "flywheel.studio-runtime-sources/v1",
        "created_at": "2026-09-15T15:00:00Z",
        "components": {
            "studio_engine": {
                "repo": "https://example.com/studio-engine.git",
                "ref": "1" * 40,
                "source_subdir": "",
                "license_notices": ["LICENSE"],
                "manifest": section(
                    "studio_engine",
                    ["pyproject.toml", "studio_engine/__init__.py"],
                    [],
                ),
            },
            "accountable_surface": {
                "repo": "https://example.com/accountable-surface.git",
                "ref": "2" * 40,
                "source_subdir": "src",
                "license_notices": ["LICENSE"],
                "manifest": section(
                    "accountable_surface",
                    ["accountable_surface/__init__.py"],
                    ["accountable_surface"],
                ),
            },
            "coherence_membrane": {
                "repo": "https://example.com/coherence-membrane.git",
                "ref": "3" * 40,
                "source_subdir": "src",
                "license_notices": ["LICENSE"],
                "manifest": section(
                    "coherence_membrane",
                    ["coherence_membrane/__init__.py"],
                    ["coherence_membrane"],
                ),
            },
            "proof_surface": {
                "repo": "https://example.com/proof-surface.git",
                "ref": "4" * 40,
                "source_subdir": "src",
                "license_notices": ["LICENSE"],
                "manifest": section(
                    "proof_surface",
                    ["proof_surface/__init__.py"],
                    ["proof_surface"],
                ),
            },
        },
    }
    path = tmp_path / "pins.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path, roots


def test_source_pins_build_manifest_from_explicit_checkouts(tmp_path):
    pins_path, roots = _pins_fixture(tmp_path)
    pins = load_source_pins(pins_path)

    manifest, notices = build_manifest_from_source_pins(pins, checkout_roots=roots)

    assert manifest["schema"] == "flywheel.studio-body-runtime-manifest/v1"
    assert manifest["studio_engine"]["root"] == str(roots["studio_engine"])
    assert manifest["accountable_surface"]["source_root"] == str(
        roots["accountable_surface"] / "src")
    assert len(notices) == 4
    assert all(path.name == "LICENSE" for path in notices)


def test_source_pins_reject_private_paths_and_non_commit_refs(tmp_path):
    pins_path, _roots = _pins_fixture(tmp_path)
    doc = json.loads(pins_path.read_text(encoding="utf-8"))
    doc["components"]["studio_engine"]["repo"] = "C:/dev/private/studio-engine"
    pins_path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(RuntimeError, match="public https URL"):
        load_source_pins(pins_path)

    doc["components"]["studio_engine"]["repo"] = "https://example.com/studio.git"
    doc["components"]["studio_engine"]["ref"] = "main"
    pins_path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(RuntimeError, match="40-hex"):
        load_source_pins(pins_path)


def test_repo_source_pins_are_ci_safe_public_commit_inputs():
    pins = load_source_pins(Path("packaging/studio-runtime-sources.json"))
    assert sorted(pins["components"]) == [
        "accountable_surface",
        "coherence_membrane",
        "proof_surface",
        "studio_engine",
    ]
    assert "C:/dev" not in json.dumps(pins)
    for component in pins["components"].values():
        assert component["repo"].startswith("https://github.com/HarperZ9/")
        assert len(component["ref"]) == 40


def test_desktop_release_stages_studio_runtime_before_pyinstaller():
    text = Path(".github/workflows/desktop-release.yml").read_text(encoding="utf-8")
    stage = text.index("Stage Studio runtime payload")
    freeze = text.index("python -m PyInstaller")
    assert stage < freeze
    assert "packaging\\studio-runtime-sources.json" in text
    assert "stage-pinned-payload" in text
    assert "FLYWHEEL_STUDIO_BODY_RUNTIME_MANIFEST" in text
    assert "FLYWHEEL_STUDIO_BODY_RUNTIME_PAYLOAD" in text


def test_workflow_packaging_entrypoint_starts_without_pythonpath():
    text = Path(".github/workflows/desktop-release.yml").read_text(encoding="utf-8")
    command = next(line.strip().split(" stage-pinned-payload", 1)[0]
                   for line in text.splitlines() if " stage-pinned-payload" in line)
    env = {key: value for key, value in os.environ.items()
           if key.upper() != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, *shlex.split(command)[1:], "--help"],
        env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "stage-pinned-payload" in result.stdout


def test_pinned_checkout_preserves_bytes_with_global_autocrlf(tmp_path, monkeypatch):
    config = tmp_path / "global.gitconfig"
    config.write_text("[core]\n\tautocrlf = true\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = tmp_path / "origin"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], stderr=subprocess.STDOUT, text=True)

    git("init")
    git("config", "core.autocrlf", "false")
    source = b"first line\nsecond line\n"
    (repo / "source.py").write_bytes(source)
    git("add", "source.py")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-m", "fixture")
    commit = git("rev-parse", "HEAD").strip()
    pins = {"components": {name: {"repo": str(repo), "ref": commit} for name in
            ("studio_engine", "accountable_surface", "coherence_membrane", "proof_surface")}}
    roots = checkout_source_pins(pins, work_root=tmp_path / "clones")
    for root in roots.values():
        assert (root / "source.py").read_bytes() == source
