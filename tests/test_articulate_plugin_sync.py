"""Verify Articulate core detector and Claude-plugin mirror stay byte-identical."""
from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_DETECTOR = REPO_ROOT / "packages" / "articulate" / "src" / "articulate" / "detector.py"
PLUGIN_DETECTOR = (
    REPO_ROOT / "packages" / "articulate" / "claude-plugin" / "src" / "articulate" / "detector.py"
)


def _files_byte_identical(path_a: Path, path_b: Path) -> tuple[bool, str, str]:
    bytes_a = path_a.read_bytes()
    bytes_b = path_b.read_bytes()
    sha_a = hashlib.sha256(bytes_a).hexdigest()
    sha_b = hashlib.sha256(bytes_b).hexdigest()
    return bytes_a == bytes_b and sha_a == sha_b, sha_a, sha_b


def test_articulate_detector_and_claude_plugin_mirror_are_byte_identical() -> None:
    assert CORE_DETECTOR.is_file(), f"missing core detector: {CORE_DETECTOR}"
    assert PLUGIN_DETECTOR.is_file(), f"missing plugin mirror: {PLUGIN_DETECTOR}"
    identical, sha_core, sha_plugin = _files_byte_identical(CORE_DETECTOR, PLUGIN_DETECTOR)
    assert identical, (
        "Articulate detector.py drifted from claude-plugin mirror: "
        f"core={sha_core} plugin={sha_plugin}"
    )


def test_sync_check_detects_single_byte_drift(tmp_path: Path) -> None:
    a = tmp_path / "core_detector.py"
    b = tmp_path / "plugin_detector.py"
    a.write_bytes(b"def detect(text):\n    return []\n")
    b.write_bytes(b"def detect(text):\n    return [1]\n")
    identical, sha_a, sha_b = _files_byte_identical(a, b)
    assert not identical
    assert sha_a != sha_b
