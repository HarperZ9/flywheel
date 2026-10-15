"""Falsifiers for the one-line installers: what they install, where, and what they leave alone."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_shell_installer_is_posix_sh_and_needs_python_311():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh") and "set -eu" in text
    assert "sys.version_info < (3, 11)" in text
    assert 'FLYWHEEL_VERSION' in text and 'flywheel-verify==' in text
    assert "sudo" not in text                       # a user install, never root


def test_powershell_installer_asks_before_touching_path():
    text = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "sys.version_info < (3, 11)" in text
    assert "-NoPath" in text and "FLYWHEEL_NO_PATH" in text
    assert '"User"' in text and '"Machine"' not in text   # never the machine PATH


def test_getting_started_ci_runs_on_three_systems_with_a_time_bar():
    wf = (ROOT / ".github" / "workflows" / "getting-started.yml").read_text(encoding="utf-8")
    for os_name in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert os_name in wf
    assert "spent < 300" in wf and "flywheel doctor" in wf and "flywheel code -p" in wf
