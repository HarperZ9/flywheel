"""Tests for Flywheel's 1-command installers (install.ps1, install.sh) and release-assets workflow."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_installer_files_and_workflow_hygiene():
    for rel in ("install.ps1", "install.sh", ".github/workflows/release-assets.yml"):
        p = ROOT / rel
        assert p.is_file(), f"missing {rel}"
        text = p.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 300, f"{rel} exceeds 300 lines"
        assert "\u2014" not in text and "\u2013" not in text, f"{rel} contains em/en dash"
        assert "SHA256SUMS" in text, f"{rel} must enforce SHA256SUMS verification"


def test_platform_one_command_installer_self_test():
    if os.name == "nt":
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install.ps1"), "-SelfTest"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        res = subprocess.run(
            ["sh", str(ROOT / "install.sh"), "--self-test"],
            capture_output=True,
            text=True,
            check=False,
        )
    assert res.returncode == 0, f"installer self-test failed: stdout={res.stdout!r} stderr={res.stderr!r}"
    assert "SELFTEST PASS" in res.stdout
