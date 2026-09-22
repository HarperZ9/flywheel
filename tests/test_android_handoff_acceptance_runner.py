import json
import shutil
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "desktop" / "tool" / "run_android_handoff_acceptance.ps1"


def test_android_handoff_runner_selftest_redacts_token_and_writes_contract(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell is not None
    receipt = tmp_path / "android-handoff-runner-selftest.json"
    result = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            "-SelfTest",
            "-ReceiptPath",
            str(receipt),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    proof = json.loads(receipt.read_text(encoding="utf-8-sig"))
    assert proof["schema"] == "flywheel.android-handoff-runner-selftest/v1"
    assert proof["mode"] == "self_test"
    assert proof["token_material"] == "generated-and-redacted"
    assert proof["device_selection"]["single_device"]["status"] == "ok"
    assert proof["device_selection"]["no_device"]["status"] == "blocked"
    assert proof["device_selection"]["duplicate_device"]["status"] == "blocked"
    assert proof["planned_flutter_test"]["contains_secret"] is False
    validation = proof["fixture_validation"]
    assert validation["valid"]["ok"] is True
    assert validation["invalid_json"]["reason"] == "invalid_fixture_receipt_json"
    assert validation["wrong_token"]["reason"] == "negative_control_not_rejected"
    assert validation["wrong_token"]["case"] == "wrong_token_rejected"
    assert validation["unreachable_endpoint"]["reason"] == "negative_control_not_rejected"
    assert validation["unreachable_endpoint"]["case"] == "unreachable_gateway"
    capture = proof["process_capture"]
    assert capture["stdout_stderr"]["exit_code"] == 0
    assert capture["stdout_stderr"]["stdout_tail_seen"] is True
    assert capture["stdout_stderr"]["stderr_tail_seen"] is True
    assert capture["timeout"]["exit_code"] == 124
    assert capture["timeout"]["timed_out"] is True
    assert capture["timeout"]["child_killed"] is True
    assert capture["batch_launch_exit_code"] == 0
    assert capture["environment_override"]["exit_code"] == 0
    assert capture["environment_override"]["stdout"] == "ok"
    assert capture["during_run_poll"]["captured"] is True
    assert capture["during_run_poll"]["polls"] > 0
    package = proof["package_status"]
    assert package["absent"]["status"] == "absent"
    assert package["absent"]["verified_absent"] is True
    assert package["present"]["status"] == "present"
    assert package["transport_error"]["status"] == "unknown"
    assert package["transport_error"]["reason"] == "adb_transport_error"
    assert package["unauthorized"]["status"] == "unknown"
    assert package["offline_device"]["reason"] == "adb_state_offline"
    assert package["stderr_diagnostic"]["reason"] == "adb_pm_diagnostic"
    assert package["malformed_stdout"]["reason"] == "malformed_pm_path_output"
    signing = proof["apk_signing"]
    assert signing["success"]["status"] == "ok"
    assert signing["success"]["certificate_sha256"] == (
        "0123456789abcdef" * 4
    )
    assert signing["java_missing"]["status"] == "unknown"
    assert signing["java_missing"]["reason"] == "java_unavailable"
    assert "JAVA_HOME is not set" in signing["java_missing"]["stdout_tail"]
    assert signing["missing_digest"]["status"] == "unknown"
    assert signing["missing_digest"]["reason"] == "missing_certificate_digest"
    binding = proof["installed_artifact_binding"]
    assert binding["matching"]["ok"] is True
    assert binding["hash_mismatch"]["ok"] is False
    assert binding["hash_mismatch"]["reason"] == "installed_package_hash_mismatch"
    assert binding["missing_signing"]["ok"] is False
    assert binding["missing_signing"]["reason"] == "missing_signing_evidence"
    drift = binding["postcapture_artifact_drift"]
    assert drift["expected_apk_sha256"] == "during"
    assert drift["capture_binding"]["ok"] is True
    assert drift["final_expected_apk_sha256"] == "final"
    assert drift["binding"]["ok"] is False
    assert drift["binding"]["reason"] == "installed_package_hash_mismatch"
    priority = proof["failure_priority"]
    assert priority["flutter_failure"] == "flutter_test_failed"
    assert priority["fixture_failure"] == "missing_fixture_receipt"
    assert priority["binding_failure"] == "tested_package_not_present"
    assert "sentinel-android-handoff-secret" not in receipt.read_text(
        encoding="utf-8-sig"
    )
    assert "sentinel-android-handoff-secret" not in result.stdout
    assert "sentinel-android-handoff-secret" not in result.stderr


def test_during_run_poll_never_hashes_flutter_build_artifact():
    text = RUNNER.read_text(encoding="utf-8-sig")
    poll = text.split(
        "$test = Invoke-Captured $flutter $args $desktopRoot 900 -OnPoll {", 1
    )[1].split("} -PollMilliseconds", 1)[0]
    assert "Get-FileSha256 $apk" not in poll
    assert "Get-TestedInstalledPackageEvidence $adb $selection.id $applicationId $null $sdkRoot" in poll
    evidence = text.split(
        "function Get-TestedInstalledPackageEvidence", 1
    )[1].split("function Set-FinalTestedPackageBinding", 1)[0]
    assert 'Read-ApkVersion (Resolve-BuildTool $SdkRoot "aapt.exe") $baseApk' in evidence
    assert 'Read-ApkSigning (Resolve-BuildTool $SdkRoot "apksigner.bat") $baseApk' in evidence

