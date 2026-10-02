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


def test_tag_checks_reject_wrong_commit_and_patch_version():
    result = ps("""
function git { $global:LASTEXITCODE = 0; return ('b' * 40) }
try { Assert-TagInstallerSource 'v1.2.0' '1.2.0' ('a' * 40); throw 'false success' }
catch { if ($_.Exception.Message -notmatch 'exact source') { throw } }
try { Assert-TagInstallerSource 'v1.2.1' '1.2.1' ('a' * 40); throw 'false success' }
catch { if ($_.Exception.Message -notmatch 'mature source') { throw } }
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
