from pathlib import Path
import shutil
import subprocess

import pytest

WORKFLOW = Path(".github/workflows/windows-installed-acceptance.yml")
HELPER = Path("desktop/tool/run_ci_installed_acceptance.ps1")
SPEC = Path("project-docs/specs/SPEC-pretag-installed-acceptance-20260915.md")
ROOT = Path(__file__).resolve().parent.parent


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _helper() -> str:
    return HELPER.read_text(encoding="utf-8")


def _spec() -> str:
    return SPEC.read_text(encoding="utf-8")


def _index(text: str, needle: str) -> int:
    assert needle in text, f"missing {needle!r}"
    return text.index(needle)


def _ps_literal(path: Path | str) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _run_helper_ps(body: str, cwd: Path | None = None) -> str:
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if exe is None:
        pytest.skip("PowerShell unavailable")
    code = f". {_ps_literal((ROOT / HELPER).resolve())} -DefineOnly\n{body}"
    completed = subprocess.run(
        [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", code],
        cwd=cwd or ROOT, text=True, capture_output=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def test_workflow_is_manual_read_only_windows_runner():
    text = _workflow()

    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "tags:" not in text
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "runs-on: windows-latest" in text
    assert "timeout-minutes:" in text


def test_workflow_passes_commit_only_through_env_and_delegates_to_helper():
    text = _workflow()

    assert text.count("${{ inputs.commit }}") == 1
    assert "ACCEPTANCE_COMMIT: ${{ inputs.commit }}" in text
    assert "github.event.inputs" not in text
    assert "desktop\\tool\\run_ci_installed_acceptance.ps1" in text
    assert "expected_installer_sha" not in text.lower()
    assert "98600dac" not in text


def test_workflow_uploads_only_allowlisted_sanitized_artifacts():
    text = _workflow()

    assert "actions/upload-artifact@" in text
    for expected in (
        "desktop/build/installer/SHA256SUMS.txt",
        "desktop/build/installer/installed-build-manifest.json",
        "desktop/build/installer/ci-installed-acceptance-summary.json",
        "desktop/build/installer/python-lane-source-stage.json",
        "desktop/build/installer/frozen-gateway-smoke.json",
        "desktop/build/installer/installed-acceptance/*.json",
    ):
        assert expected in text
    assert "if-no-files-found: error" in text
    assert "*.stdout.log" not in text
    assert "*.stderr.log" not in text
    assert "$env:RUNNER_TEMP" not in text
    assert "**" not in text
    assert "AppData" not in text
    assert "C:\\Users" not in text


def test_helper_validates_commit_repository_and_reachability_before_checkout():
    text = _helper()

    assert "^[0-9a-f]{40}$" in text
    assert "Assert-WorkflowSource $targetCommit" in text
    assert "GITHUB_SHA must exactly match ACCEPTANCE_COMMIT" in text
    assert "EXPECTED_REPOSITORY" in text
    assert "HarperZ9/flywheel" in text
    assert "branch --remotes --contains" in text
    assert '@("checkout", "--detach", $targetCommit)' in text
    assert _index(text, "^[0-9a-f]{40}$") < _index(text, '@("checkout", "--detach", $targetCommit)')
    assert _index(text, "branch --remotes --contains") < _index(text, '@("checkout", "--detach", $targetCommit)')
    assert "rev-parse HEAD" in text


def test_helper_verifies_target_tools_and_tracked_source_identity():
    text = _helper()

    assert "Assert-RequiredTargetFiles" in text
    for expected in (
        "desktop\\tool\\run_installed_launch_acceptance.ps1",
        "desktop\\tool\\installed_payload_binding.py",
        "desktop\\scripts\\build_installer.ps1",
        "scripts\\studio_runtime_packaging.py",
        "scripts\\stage_python_lane_sources.py",
        "packaging\\flywheel-gateway.spec",
    ):
        assert expected in text
    assert "Assert-CleanWorkspaceNoUntracked \"before build\"" in text
    assert "Assert-TrackedAndSubmodulesUnchanged \"after build\"" in text
    assert "Assert-TrackedAndSubmodulesUnchanged \"after acceptance\"" in text
    assert "git -C $Root status --porcelain=v1 --untracked-files=all --ignore-submodules=none" in text
    assert "git -C $Root submodule status --recursive" in text
    assert "Write-SourceDriftDiagnostics $Label $Root" in text
    assert "git -C $Root diff --name-status --ignore-submodules" in text
    assert "git -C $Root ls-files --eol -- $paths" in text
    assert "git -C $Root hash-object --no-filters -- $path" in text


def test_flutter_generated_plugin_registrants_are_lf_pinned():
    text = Path(".gitattributes").read_text(encoding="utf-8")

    for expected in (
        "desktop/linux/flutter/generated_plugin_registrant.* text eol=lf",
        "desktop/linux/flutter/generated_plugins.cmake text eol=lf",
        "desktop/macos/Flutter/GeneratedPluginRegistrant.swift text eol=lf",
        "desktop/windows/flutter/generated_plugin_registrant.* text eol=lf",
        "desktop/windows/flutter/generated_plugins.cmake text eol=lf",
    ):
        assert expected in text


def test_helper_source_drift_diagnostics_keep_real_edits_blocking(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "source.txt"
    source.write_text("before\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "add", "source.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    source.write_text("after\n", encoding="utf-8", newline="\n")
    root = _ps_literal(tmp_path)

    out = _run_helper_ps(f"""
try {{ Assert-TrackedAndSubmodulesUnchanged 'dirty' -Root {root}; throw 'expected failure' }}
catch {{ if ($_.Exception.Message -notmatch 'changed tracked source files') {{ throw }} }}
'OK'
""")

    assert "dirty git status porcelain:  M source.txt" in out
    assert "dirty git diff --name-status: M\tsource.txt" in out
    assert "dirty byte hash source.txt head=" in out
    assert "OK" in out


def test_helper_stages_every_lane_source_before_installed_freeze_with_bounded_receipt():
    text = _helper()

    studio = _index(text, "stage pinned Studio runtime")
    stage = _index(text, "stage Python lane sources")
    env = _index(text, "FLYWHEEL_PYTHON_LANE_SOURCE_ROOT")
    freeze = _index(text, "freeze gateway")
    assert studio < stage < env < freeze
    assert 'Join-Path $env:RUNNER_TEMP "flywheel-python-lane-sources"' in text
    assert "stage_python_lane_sources.py\", \"--all\"" in text
    assert "--lane\", \"canon\"" not in text
    assert "--bounded-receipt\", $pythonLaneBoundedReceipt" in text
    assert 'Join-Path $installerDir "python-lane-source-stage.json"' in text


def test_helper_rejects_dispatch_sha_mismatch_before_checkout():
    target = "a" * 40
    other = "b" * 40
    out = _run_helper_ps(f"""
$env:GITHUB_SHA = '{other}'
try {{ Assert-WorkflowSource '{target}'; throw 'expected failure' }}
catch {{ if ($_.Exception.Message -notmatch 'GITHUB_SHA') {{ throw }} }}
$env:GITHUB_SHA = '{target}'
Assert-WorkflowSource '{target}'
'OK'
""")
    assert "OK" in out


def test_helper_workspace_gate_rejects_untracked_files(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    root = _ps_literal(tmp_path)
    assert "OK" in _run_helper_ps(
        f"Assert-CleanWorkspaceNoUntracked 'clean' -Root {root}\n'OK'")
    (tmp_path / "extra.txt").write_text("x", encoding="utf-8")
    out = _run_helper_ps(f"""
try {{ Assert-CleanWorkspaceNoUntracked 'dirty' -Root {root}; throw 'expected failure' }}
catch {{ if ($_.Exception.Message -notmatch 'not clean before build') {{ throw }} }}
'OK'
""")
    assert "OK" in out


def test_helper_records_ci_candidate_hashes_before_install_and_binds_acceptance():
    text = _helper()

    assert _index(text, "Get-FileHash -LiteralPath $installer.FullName") < _index(text, "Start-Process")
    assert "installerHashBeforeInstall" in text
    assert "installer hash changed before installation" in text
    assert "SHA256SUMS.txt" in text
    assert "installed_payload_binding" in text
    assert "artifacts.app_sha256" in text
    assert "artifacts.engine_sha256" in text
    for expected in (
        "-BuildManifest", "$buildManifest",
        "-SourceCommitExpected", "$targetCommit",
        "-ExpectedAppSha256", "$appHash",
        "-ExpectedEngineSha256", "$engineHash",
    ):
        assert expected in text
    assert "98600dac" not in text


def test_helper_requires_clean_runner_and_checked_silent_per_user_install():
    text = _helper()

    assert "Assert-CleanFlywheelHost" in text
    assert "Get-PropertyText" in text
    assert "Assert-RegistryInstallLocation" in text
    assert "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*" in text
    assert "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*" in text
    assert "/CURRENTUSER" in text
    assert "/VERYSILENT" in text
    assert "/SUPPRESSMSGBOXES" in text
    assert "-WindowStyle Hidden" in text
    assert "-Wait" in text
    assert "-PassThru" in text
    assert "$install.ExitCode -ne 0" in text
    assert "Remove-Item" not in text
    assert "git clean" not in text


def test_helper_registry_helpers_are_strictmode_safe_and_require_requested_root():
    root = r"C:\Users\runner\AppData\Local\Programs\Flywheel"
    out = _run_helper_ps(f"""
$plain = [pscustomobject]@{{ PSChildName = 'plain-entry' }}
if (RegistryEntryMatchesFlywheel $plain) {{ throw 'plain entry matched' }}
$entry = [pscustomobject]@{{ PSChildName = '{{ecf4cc9b-8a7a-4de2-8e70-0f1ea0f17e5c}}_is1'; InstallLocation = '{root}\\' }}
Assert-RegistryInstallLocation $entry '{root}'
$missing = [pscustomobject]@{{ PSChildName = '{{ecf4cc9b-8a7a-4de2-8e70-0f1ea0f17e5c}}_is1' }}
try {{ Assert-RegistryInstallLocation $missing '{root}'; throw 'expected failure' }}
catch {{ if ($_.Exception.Message -notmatch 'missing InstallLocation') {{ throw }} }}
$wrong = [pscustomobject]@{{ PSChildName = '{{ecf4cc9b-8a7a-4de2-8e70-0f1ea0f17e5c}}_is1'; InstallLocation = 'C:\\Other\\Flywheel' }}
try {{ Assert-RegistryInstallLocation $wrong '{root}'; throw 'expected failure' }}
catch {{ if ($_.Exception.Message -notmatch 'does not match requested') {{ throw }} }}
'OK'
""")
    assert "OK" in out


def test_helper_acceptance_arg_builder_returns_flat_string_array():
    out = _run_helper_ps(r"""
$common = @('-InstallRoot', 'C:\Flywheel', '-BuildManifest', 'manifest.json')
$args = New-InstalledAcceptanceCommandArgs -Runner 'runner.ps1' -Common $common -ValidationDir 'v' -Out 'o' -Mode 'full' -StartEngine
if (@($args | Where-Object { $_ -isnot [string] -or $_ -eq 'System.Object[]' }).Count -ne 0) { throw 'non-flat args' }
$expected = '-NoProfile|-ExecutionPolicy|Bypass|-File|runner.ps1|-InstallRoot|C:\Flywheel|-BuildManifest|manifest.json|-ValidationDir|v|-Out|o|-Mode|full|-StartEngine'
if (($args -join '|') -ne $expected) { throw (($args -join '|')) }
'OK'
""")
    assert "OK" in out


def test_helper_runs_full_and_inspect_acceptance_without_publication_side_effects():
    text = _helper()

    assert "New-InstalledAcceptanceCommandArgs $runner $common $fullDir $fullReceipt \"full\" -StartEngine" in text
    assert "New-InstalledAcceptanceCommandArgs $runner $common $inspectDir $inspectReceipt \"inspect\" -InspectImport" in text
    assert "-InspectImport" in text
    assert "tests\\fixtures\\inspect\\v1\\single-success.fixture.json" in text
    for forbidden in ("gh release", "publish_token", "contents: write", "GITHUB_TOKEN"):
        assert forbidden not in text


def test_spec_documents_boundaries_and_non_bit_reproducibility():
    text = _spec().lower()

    assert "does not claim bit reproducibility" in text
    assert "does not accept any older local installer" in text
    assert "does not prove native ui" in text
    assert "no broad temp directories" in text
    assert "workflow_dispatch" in text



