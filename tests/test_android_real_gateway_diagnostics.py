import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "desktop" / "tool" / "run_android_real_gateway_handoff_acceptance.ps1"
SUPPORT = REPO / "desktop" / "tool" / "android_real_gateway_runner_support.ps1"


def _shell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell is not None
    return shell


def _ps_literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _run_support_json(tmp_path: Path, body: str) -> dict:
    script = tmp_path / "diagnostic-probe.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            Set-StrictMode -Version Latest
            . {_ps_literal(SUPPORT)}
            {body}
            """
        ).strip(),
        encoding="utf-8",
    )
    result = subprocess.run(
        [_shell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return json.loads(result.stdout)


def test_phase_evidence_preserves_complete_diagnostics_and_redacts_secrets(tmp_path):
    proof = _run_support_json(
        tmp_path,
        r"""
        $RunId = 'android_real_diagnostics_probe'
        $Token = 'tok-secret-123.abc'
        $Device = 'emulator-5554'
        $BearerSecret = 'bearerSecret-456.def'
        $receipt = @{
          schema = 'flywheel.android-real-gateway-handoff-phase/v1'
          run_id = $RunId
          phase = 'start'
          platform = 'android'
          request_sha256 = ('a' * 64)
          operation_refs = @('op_start')
        } | ConvertTo-Json -Compress
        $padding = @(1..750 | ForEach-Object {
          "padding-$($_) $Token $Device Bearer $BearerSecret"
        }) -join "`n"
        $stdout = "FIRST_FLUTTER_ERROR before old tail $Token Bearer $BearerSecret $Device`n$padding`nFLYWHEEL_ANDROID_REAL_GATEWAY_HANDOFF_RECEIPT_JSON:$receipt`nEND_STDOUT_DIAGNOSTIC"
        $stderr = "FIRST_STDERR_DIAGNOSTIC $Token $Device`n$padding`nEND_STDERR_DIAGNOSTIC Bearer stderrSecret-789"
        $args = @('test', '-d', $Device, "--dart-define=TOKEN=$Token", "--header=Bearer $BearerSecret")
        $result = @{ exit_code = 17; stdout = $stdout; stderr = $stderr }
        $redacted = Redact-GatewayText $stdout $Token $Device
        $evidence = New-RealPhaseEvidence $result $args $RunId 'start' $Token $Device
        $encodedEvidence = $evidence | ConvertTo-Json -Depth 32 -Compress
        @{
          redacted_text = @{
            has_first = $redacted.Contains('FIRST_FLUTTER_ERROR')
            has_middle = $redacted.Contains('padding-375')
            has_end = $redacted.Contains('END_STDOUT_DIAGNOSTIC')
            length = $redacted.Length
            token_leaked = $redacted.Contains($Token)
            bearer_leaked = $redacted.Contains("Bearer $BearerSecret")
            device_leaked = $redacted.Contains($Device)
            bearer_redacted = $redacted.Contains('Bearer [redacted]')
          }
          evidence = $evidence
          evidence_json_leaked = (
            $encodedEvidence.Contains($Token) -or
            $encodedEvidence.Contains($Device) -or
            $encodedEvidence.Contains($BearerSecret) -or
            $encodedEvidence.Contains('stderrSecret-789')
          )
        } | ConvertTo-Json -Depth 32 -Compress
        """,
    )

    redacted = proof["redacted_text"]
    assert redacted["has_first"] is True
    assert redacted["has_middle"] is True
    assert redacted["has_end"] is True
    assert redacted["length"] > 6000
    assert redacted["token_leaked"] is False
    assert redacted["bearer_leaked"] is False
    assert redacted["device_leaked"] is False
    assert redacted["bearer_redacted"] is True

    evidence = proof["evidence"]
    assert evidence["exit_code"] == 17
    assert evidence["validation"] == {"ok": True, "reason": "ok"}
    assert evidence["receipt"]["run_id"] == "android_real_diagnostics_probe"
    assert evidence["receipt"]["phase"] == "start"
    assert evidence["stdout"].startswith("FIRST_FLUTTER_ERROR")
    assert "padding-375" in evidence["stdout"]
    assert evidence["stdout"].endswith("END_STDOUT_DIAGNOSTIC")
    assert evidence["stderr"].startswith("FIRST_STDERR_DIAGNOSTIC")
    assert evidence["stderr"].endswith("Bearer [redacted]")
    assert "END_STDOUT_DIAGNOSTIC" in evidence["stdout_tail"]
    assert "END_STDERR_DIAGNOSTIC" in evidence["stderr_tail"]
    assert all("emulator-5554" not in arg for arg in evidence["args"])
    assert all("tok-secret-123.abc" not in arg for arg in evidence["args"])
    assert proof["evidence_json_leaked"] is False


def test_android_screen_readiness_requires_visible_unlocked_awake_policy(tmp_path):
    proof = _run_support_json(
        tmp_path,
        r"""
        $cases = @(
          @{ name = 'ready'; text = "showing=false`nscreenState=SCREEN_STATE_ON`ninteractiveState=INTERACTIVE_STATE_AWAKE" }
          @{ name = 'locked'; text = "showing=true`nscreenState=SCREEN_STATE_ON`ninteractiveState=INTERACTIVE_STATE_AWAKE" }
          @{ name = 'missing_screen_state'; text = "showing=false`ninteractiveState=INTERACTIVE_STATE_AWAKE" }
          @{ name = 'contradictory_lock_state'; text = "showing=false`nshowing=true`nscreenState=SCREEN_STATE_ON`ninteractiveState=INTERACTIVE_STATE_AWAKE" }
          @{ name = 'sleeping'; text = "showing=false`nscreenState=SCREEN_STATE_OFF`ninteractiveState=INTERACTIVE_STATE_SLEEP" }
        )
        @($cases | ForEach-Object {
          $actual = Test-AndroidScreenReadiness $_.text
          @{ name = $_.name; ok = $actual.ok; reason = $actual.reason }
        }) | ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert {row["name"]: {"ok": row["ok"], "reason": row["reason"]} for row in proof} == {
        "ready": {"ok": True, "reason": "ok"},
        "locked": {"ok": False, "reason": "android_screen_locked"},
        "missing_screen_state": {"ok": False, "reason": "android_screen_state_unknown"},
        "contradictory_lock_state": {
            "ok": False,
            "reason": "android_screen_state_unknown",
        },
        "sleeping": {"ok": False, "reason": "android_screen_not_awake"},
    }


@pytest.mark.skipif(
    os.name != "nt",
    reason="stubs adb and flutter as Windows .cmd shims, which a Linux runner "
           "cannot execute even though it has pwsh")
def test_runner_stops_before_package_or_flutter_when_connected_screen_is_locked(tmp_path):
    adb_log = tmp_path / "adb.log"
    flutter_log = tmp_path / "flutter.log"
    receipt = tmp_path / "receipt.json"
    adb = tmp_path / "adb.cmd"
    flutter = tmp_path / "flutter.cmd"
    adb.write_text(
        textwrap.dedent(
            r"""
            @echo off
            echo %*>>"%FW_FAKE_ADB_LOG%"
            if "%~1"=="devices" (
              echo List of devices attached
              echo synthetic-device	device
              exit /b 0
            )
            if "%~1"=="-s" if "%~2"=="synthetic-device" if "%~3"=="shell" if "%~4"=="dumpsys" (
              echo showing=true
              echo screenState=SCREEN_STATE_ON
              echo interactiveState=INTERACTIVE_STATE_AWAKE
              exit /b 0
            )
            echo unexpected adb command %* 1>&2
            exit /b 42
            """
        ).strip(),
        encoding="utf-8",
    )
    flutter.write_text(
        textwrap.dedent(
            r"""
            @echo off
            echo %*>>"%FW_FAKE_FLUTTER_LOG%"
            exit /b 99
            """
        ).strip(),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["FW_FAKE_ADB_LOG"] = str(adb_log)
    env["FW_FAKE_FLUTTER_LOG"] = str(flutter_log)

    result = subprocess.run(
        [
            _shell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            "-AdbPath",
            str(adb),
            "-FlutterPath",
            str(flutter),
            "-PythonPath",
            sys.executable,
            "-ReceiptPath",
            str(receipt),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )

    assert result.returncode == 1
    proof = json.loads(receipt.read_text(encoding="utf-8-sig"))
    assert proof["status"] == "blocked"
    assert proof["blocker"] == "android_screen_locked"
    assert proof["device_selection"] == {"status": "ok", "reason": None}
    assert proof["screen_preflight"] == {
        "ok": False,
        "reason": "android_screen_locked",
    }
    assert "package_policy" not in proof
    assert "build" not in proof
    assert "install" not in proof
    assert "phases" not in proof
    adb_commands = adb_log.read_text(encoding="utf-8").replace('"', "")
    assert "devices" in adb_commands
    assert "dumpsys window policy" in adb_commands
    assert "pm path" not in adb_commands
    assert "install" not in adb_commands
    assert not flutter_log.exists()


def test_pc_operation_set_rejects_null_without_counting_phantom_operation(tmp_path):
    proof = _run_support_json(
        tmp_path,
        r"""
        Test-RealPcOperationSet $null ('a' * 64) 'op_expected' |
          ConvertTo-Json -Depth 8 -Compress
        """,
    )

    assert proof["ok"] is False
    assert proof["reason"] == "pc_operation_set_mismatch"
    assert proof["operation_count"] == 0
