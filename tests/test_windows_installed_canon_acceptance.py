"""Keep the Canon probe bound to the post-install path and fatal on failure."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "desktop/tool/run_ci_installed_acceptance.ps1"


def test_canon_probe_runs_after_installed_binding_before_success_summary():
    text = HELPER.read_text(encoding="utf-8")
    registry = text.index("Assert-RegistryInstallLocation $entries[0] $requestedInstallRoot")
    full = text.index('Invoke-Checked "full installed acceptance"')
    inspect = text.index('Invoke-Checked "inspect installed acceptance"')
    canon = text.index('Invoke-Checked "installed Canon context acceptance"')
    unchanged = text.index('Assert-TrackedAndSubmodulesUnchanged "after acceptance"')
    summary = text.index('$summary = [ordered]@{')
    assert registry < full < inspect < canon < unchanged < summary
    call = text[canon:text.index("\n", canon)]
    for binding in (
        '"scripts/check_installed_canon_context.py"',
        '"--install-root", $requestedInstallRoot',
        '"--expected-engine-sha256", $engineHash',
        '"--expected-version", $version',
        '"--source-commit", $targetCommit',
        '"--receipt", $canonReceipt',
    ):
        assert binding in call
    assert "dist/" not in call and "engineStage" not in call


def test_canon_receipt_is_linked_and_already_within_narrow_upload_allowlist():
    text = HELPER.read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/windows-installed-acceptance.yml").read_text()
    assert '$canonReceipt = Join-Path $acceptanceDir "installed-canon-context.json"' in text
    assert 'canon_context = "installed-acceptance/installed-canon-context.json"' in text
    assert '"scripts\\check_installed_canon_context.py"' in text
    assert '"desktop\\tool\\installed_acceptance_commands.ps1"' in text
    assert "desktop/build/installer/installed-acceptance/*.json" in workflow
    assert "**" not in workflow


def test_shared_commands_are_sourced_from_helper_directory():
    text = HELPER.read_text(encoding="utf-8")
    assert '. (Join-Path $scriptRoot "installed_acceptance_commands.ps1")' in text
    shared = (ROOT / "desktop/tool/installed_acceptance_commands.ps1").read_text()
    assert 'if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit $LASTEXITCODE" }' in shared
    assert "Pop-Location" in shared
