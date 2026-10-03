"""The release notes print the shipped rule-pack digest.

Success criteria:
- notes for the declared version exist and the check passes on them;
- false-success control: notes that print a different 64-hex digest fail.
"""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("check_release_digest",
                                              ROOT / "scripts" / "check_release_digest.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_notes_print_the_shipped_digest():
    # check() passes vacuously when no notes exist, so pin that they do.
    assert (ROOT / f"RELEASE-NOTES-{mod.declared_version()}.md").exists()
    assert mod.check() == []


def test_control_a_wrong_digest_fails(tmp_path):
    version = mod.declared_version()
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    (tmp_path / f"RELEASE-NOTES-{version}.md").write_text(
        f"# Flywheel {version}\n\nDigest: {'0' * 64}\n", encoding="utf-8")
    assert mod.check(tmp_path) != []
