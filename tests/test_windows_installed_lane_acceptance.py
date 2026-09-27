"""The pre-tag installed acceptance runs the lane acceptance on the installed build.

``desktop/tool/run_installed_lane_acceptance.ps1`` runs
``scripts/installed_app_lane_acceptance.py`` against the per-user install the
CI helper made, then uninstalls it, installs the same installer for all users
into Program Files and runs the lane acceptance again (PLAN WP11 step 1, O-15).
Receipts land in the uploaded folder; the detail files and throwaway homes stay
in the runner's temp folder.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "desktop/tool/run_ci_installed_acceptance.ps1"
LANE_STEP = ROOT / "desktop/tool/run_installed_lane_acceptance.ps1"
WORKFLOW = ROOT / ".github/workflows/windows-installed-acceptance.yml"


def _ps(body: str) -> str:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if exe is None:
        pytest.skip("PowerShell unavailable")
    literal = "'" + str(LANE_STEP).replace("'", "''") + "'"
    completed = subprocess.run(
        [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
         f". {literal} -DefineOnly\n{body}"],
        cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def test_ci_helper_requires_and_runs_the_lane_step_after_the_canon_step():
    text = HELPER.read_text(encoding="utf-8")
    assert "scripts\\installed_app_lane_acceptance.py" in text
    assert "run_installed_lane_acceptance.ps1" in text
    assert text.index("installed Canon context acceptance") < text.index(
        '"installed lane acceptance"') < text.index(
        'Assert-TrackedAndSubmodulesUnchanged "after acceptance"')
    assert "installed-lanes-per-user.json" in text
    assert len(text.splitlines()) <= 300


def test_lane_step_runs_per_user_then_all_users_and_uninstalls_each():
    text = LANE_STEP.read_text(encoding="utf-8")
    per_user = text.index('Invoke-LaneAcceptance $InstallRoot "per-user"')
    uninstall = text.index("Uninstall-Flywheel $InstallRoot")
    all_users = text.index("Install-AllUsers $Installer")
    assert per_user < uninstall < all_users
    assert '"/ALLUSERS"' in text and "$env:ProgramFiles" in text
    assert "Uninstall-Flywheel $allUsersRoot" in text
    assert len(text.splitlines()) <= 300


def test_lane_step_keeps_detail_and_homes_out_of_the_uploaded_folder():
    # Path.Combine joins with the host's separator: a backslash on the Windows
    # runner the step runs on, a slash under PowerShell on a Linux runner. The
    # folders each path lands in are what this test checks.
    sep, out = _ps("""
$a = Get-LaneAcceptanceArgs -Root 'C:\\Fw' -Mode 'all-users' -AcceptanceDir 'D:\\up' `
  -WorkRoot 'T:\\tmp' -SourceCommit ('a' * 40) -EngineSha256 ('b' * 64)
[System.IO.Path]::DirectorySeparatorChar
$a -join '|'
""").strip().splitlines()
    assert sep == ("\\" if os.name == "nt" else "/")
    parts = out.split("|")
    assert parts[0] == "scripts/installed_app_lane_acceptance.py"
    assert parts[parts.index("--receipt") + 1] == "D:\\up" + sep + "installed-lanes-all-users.json"
    assert parts[parts.index("--work") + 1].startswith("T:\\tmp" + sep)
    assert parts[parts.index("--detail") + 1].startswith("T:\\tmp" + sep)
    assert parts[parts.index("--install-mode") + 1] == "all-users"
    assert "source_commit=" + "a" * 40 in parts


def test_workflow_uploads_the_lane_receipts_and_allows_the_extra_time():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "desktop/build/installer/installed-acceptance/*.json" in text
    assert "detail" not in text
    assert "timeout-minutes: 120" in text and "timeout-minutes: 105" in text
