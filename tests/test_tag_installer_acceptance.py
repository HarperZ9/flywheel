"""The published candidate must contain the exact installer that passed installed checks."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_both_build_paths_reuse_one_non_building_acceptance_phase():
    source = (ROOT / 'desktop/tool/run_ci_installed_acceptance.ps1').read_text()
    tag = (ROOT / 'desktop/tool/run_tag_installed_acceptance.ps1').read_text()
    shared = (ROOT / 'desktop/tool/installed_acceptance_phase.ps1').read_text()
    assert 'installed_acceptance_phase.ps1' in source and 'installed_acceptance_phase.ps1' in tag
    for content in (tag, shared):
        assert 'PyInstaller' not in content and 'build_installer.ps1' not in content
    for label in ('full installed acceptance', 'inspect installed acceptance',
                  'installed Canon context acceptance', 'installed tool profile acceptance',
                  'installed native UI acceptance', 'installed lane acceptance'):
        assert label in shared
    assert 'Assert-CleanFlywheelHost' in shared
    assert '$ExpectedInstallerSha256' in shared and '$installerHashAfterAcceptance' in shared
    assert 'github-hosted' in shared and 'GITHUB_ACTIONS' in shared
    assert 'refs/tags/$Tag' in tag and 'Assert-WorkflowSource $targetCommit' in tag
    assert 'Assert-CleanWorkspaceNoUntracked' in tag
    assert all(len(content.splitlines()) <= 300 for content in (source, tag, shared))


def test_tag_candidate_acceptance_precedes_upload_and_carries_receipts():
    workflow = (ROOT / '.github/workflows/desktop-release.yml').read_text()
    probe = workflow.index('run_tag_installed_acceptance.ps1')
    assert workflow.index('Build and qualify the matching native MCPB') < probe
    assert probe < workflow.index('Assemble a stable candidate directory') < workflow.index('Stage the candidate artifact')
    for item in ('installed-build-manifest.json', 'ci-installed-acceptance-summary.json',
                 'installed-acceptance/*.json'):
        assert item in workflow
    assert 'if: always()' in workflow  # Failed sanitized receipts remain inspectable.
    publish = (ROOT / '.github/workflows/windows-publish.yml').read_text()
    assert publish.index('scripts/verify_installed_candidate.py') < publish.index('gh release create')
    lanes = (ROOT / 'desktop/tool/run_installed_lane_acceptance.ps1').read_text()
    assert lanes.index('$actualHash -cne $InstallerSha256') < lanes.index('"/ALLUSERS"')


def ps(body):
    shell = shutil.which('powershell') or shutil.which('pwsh')
    if shell is None:
        pytest.skip('PowerShell required')
    entry = str(ROOT / 'desktop/tool/run_tag_installed_acceptance.ps1').replace("'", "''")
    result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', f". '{entry}' -DefineOnly\n" + body],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_tag_checks_reject_wrong_commit():
    result = ps("""
function git { $global:LASTEXITCODE = 0; return ('b' * 40) }
try { Assert-TagInstallerSource 'v1.2.0' '1.2.0' ('a' * 40); throw 'false success' }
catch { if ($_.Exception.Message -notmatch 'exact source') { throw } }
try { Assert-TagInstallerSource 'v1.2.1' '1.2.1' ('a' * 40); throw 'false success' }
catch { if ($_.Exception.Message -notmatch 'exact source') { throw } }
'PASS'
""")
    assert 'PASS' in result


def test_tag_checks_accept_minor_and_patch_release_tags():
    # 1.2.0 shipped no installer: its tag carried a broken workflow, and this
    # check rejected every patch tag, so a fixed 1.2.1 could not be accepted.
    result = ps("""
function git { $global:LASTEXITCODE = 0; return ('a' * 40) }
foreach ($v in @('1.2.0', '1.2.1', '1.10.12', '2.0.0')) { Assert-TagInstallerSource "v$v" $v ('a' * 40) }
'PASS'
""")
    assert 'PASS' in result


def test_tag_checks_reject_non_release_tags():
    result = ps("""
function git { $global:LASTEXITCODE = 0; return ('a' * 40) }
$cases = @(@('v1.2.1', '1.2.0'), @('v1.2', '1.2'), @('v1.2.1-rc1', '1.2.1-rc1'),
           @('v1.2.1+28', '1.2.1+28'), @('v01.2.1', '01.2.1'), @('V1.2.1', '1.2.1'),
           @('v1.2.1.0', '1.2.1.0'), @('1.2.1', '1.2.1'))
foreach ($case in $cases) {
  try { Assert-TagInstallerSource $case[0] $case[1] ('a' * 40); throw "false success $($case[0])" }
  catch { if ($_.Exception.Message -notmatch 'release source version') { throw } }
}
'PASS'
""")
    assert 'PASS' in result


def test_checksum_name_bound_and_rejects_ambiguous_installer(tmp_path):
    (tmp_path / 'Flywheel-Setup-1.2.0.exe').write_bytes(b'fixture only')
    (tmp_path / 'SHA256SUMS.txt').write_text('a' * 64 + '  Flywheel-Setup-1.2.0.exe\n')
    literal = str(tmp_path).replace("'", "''")
    assert 'PASS' in ps(f"$installerDir = '{literal}'\nif ((Read-ExpectedInstallerHash) -cne ('a' * 64)) {{ throw 'hash' }}\n'PASS'")
    (tmp_path / 'Flywheel-Setup-other.exe').write_bytes(b'fixture only')
    assert 'PASS' in ps(f"""$installerDir = '{literal}'
try {{ Read-ExpectedInstallerHash; throw 'false success' }}
catch {{ if ($_.Exception.Message -notmatch 'filename mismatch') {{ throw }} }}
'PASS'
""")


def test_shared_phase_refuses_operator_host_before_install():
    result = ps("""
$env:GITHUB_ACTIONS = 'false'
function Start-Process { throw 'must not install' }
try { . (Join-Path $scriptRoot 'installed_acceptance_phase.ps1'); throw 'false success' }
catch { if ($_.Exception.Message -notmatch 'disposable GitHub-hosted') { throw } }
'PASS'
""")
    assert 'PASS' in result


def test_installer_checksum_rows_are_lf_terminated():
    # Both writers of desktop/build/installer/SHA256SUMS.txt: the release step and
    # the shared acceptance phase, which rewrites the file after its own hash check.
    shared = (ROOT / 'desktop/tool/installed_acceptance_phase.ps1').read_text()
    writer = next(line for line in shared.splitlines() if '"SHA256SUMS.txt"' in line)
    assert 'Out-File' not in writer and 'WriteAllText' in writer and '`n"' in writer


def test_tag_checks_read_an_lf_checksum_file(tmp_path):
    (tmp_path / 'Flywheel-Setup-1.2.1-x64.exe').write_bytes(b'fixture only')
    (tmp_path / 'SHA256SUMS.txt').write_bytes(b'b' * 64 + b'  Flywheel-Setup-1.2.1-x64.exe\n')
    literal = str(tmp_path).replace("'", "''")
    assert 'PASS' in ps(f"$installerDir = '{literal}'\nif ((Read-ExpectedInstallerHash) -cne ('b' * 64)) {{ throw 'hash' }}\n'PASS'")
