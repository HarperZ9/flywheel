import json
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RUNNER = REPO / "desktop" / "tool" / "run_android_real_gateway_handoff_acceptance.ps1"
SUPPORT = REPO / "desktop" / "tool" / "android_real_gateway_runner_support.ps1"
FIXTURE = REPO / "desktop" / "integration_test" / "android_real_gateway_handoff_test.dart"
SENTINEL = "sentinel-android-real-gateway-secret"


def _shell() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell is not None
    return shell


def _ps_literal(value: Path | str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def test_android_real_gateway_runner_selftest_models_usb_reverse_and_redacts_token(tmp_path):
    receipt = tmp_path / "android-real-gateway-runner-selftest.json"
    result = subprocess.run(
        [
            _shell(),
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
    assert proof["schema"] == "flywheel.android-real-gateway-handoff-runner-selftest/v1"
    assert proof["mode"] == "self_test"
    assert proof["transport"] == {"mode": "usb_reverse", "lan_modes": "not_implemented"}
    assert proof["token_material"] == "run_as_stdin_redacted"
    assert proof["package_policy"]["requires_absent_package"] is True
    assert proof["package_policy"]["clear_data"] is False
    assert proof["package_policy"]["cleanup_owned_install"] is True
    assert proof["connection_seed"]["uses_run_as_stdin"] is True
    assert proof["connection_seed"]["command_contains_secret"] is False
    assert proof["state_preservation"]["flutter_test_uninstall_disabled"] is True
    assert proof["state_preservation"]["checks_app_private_sentinel"] is True
    assert proof["receipt_binding"]["binds_built_apk_sha256"] is True
    assert proof["receipt_binding"]["binds_installed_apk_sha256"] is True
    assert proof["receipt_binding"]["uses_signature_helper"] is True
    phases = proof["flutter_phase_args"]
    assert [phase["phase"] for phase in phases] == ["start", "recover"]
    for phase in phases:
        joined = " ".join(phase["args"])
        assert "--no-uninstall" in phase["args"]
        assert "FLYWHEEL_ANDROID_REAL_GATEWAY_TOKEN" not in joined
        assert SENTINEL not in joined
        assert "http://127.0.0.1" not in joined
    assert proof["negative_controls"]["missing_token_rejected"] is True
    assert proof["negative_controls"]["wrong_token_rejected"] is True
    assert proof["negative_controls"]["no_duplicate_dispatch_required"] is True
    build_gate = proof["build_gate"]
    assert build_gate["failed_build"]["may_install"] is False
    assert build_gate["missing_apk_after_success"]["may_install"] is False
    assert build_gate["successful_build"]["may_install"] is True
    assert build_gate["preexisting_apk_quarantine_scoped"] is True
    duplicate = proof["duplicate_controls"]
    assert duplicate["extra_different_request"]["ok"] is False
    assert duplicate["extra_different_request"]["reason"] == "journey_operation_set_mismatch"
    assert duplicate["pc_extra_different_request"]["ok"] is False
    assert duplicate["pc_extra_different_request"]["reason"] == "pc_operation_set_mismatch"
    cleanup = proof["cleanup_gate"]
    assert cleanup["all_clean"]["ok"] is True
    assert cleanup["reverse_failure"]["ok"] is False
    assert cleanup["uninstall_failure"]["ok"] is False
    assert cleanup["gateway_still_running"]["ok"] is False
    assert cleanup["temp_root_left"]["ok"] is False
    custody = proof["remote_custody"]
    assert custody["token_write"]["ok"] is True
    assert custody["token_write"]["uses_shell"] is False
    assert custody["token_write"]["stdin_target"] == "run-as-child-dd-of"
    assert custody["compound_shell_control"]["ok"] is False
    assert custody["compound_shell_control"]["reason"] == "run_as_shell_forbidden"
    assert custody["redirection_control"]["ok"] is False
    assert custody["redirection_control"]["reason"] == "run_as_metachar_forbidden"
    assert custody["invalid_path_control"]["ok"] is False
    assert custody["invalid_path_control"]["reason"] == "run_as_path_forbidden"
    assert custody["lifecycle_functions"]["start_isolated_gateway_resolves"] is True
    assert custody["lifecycle_functions"]["stop_owned_gateway_resolves"] is True
    stdio = proof["gateway_stdio_process"]
    assert stdio["nonzero_exit"]["startup_state"] == "process_exited_before_token"
    assert stdio["nonzero_exit"]["cleanup"]["exit_code"] == 7
    assert "dummy fail stdout" in stdio["nonzero_exit"]["cleanup"]["stdout_tail"]
    assert "dummy fail stderr" in stdio["nonzero_exit"]["cleanup"]["stderr_tail"]
    assert stdio["success"]["alive"] is True
    assert stdio["success"]["cleanup"]["stopped"] is True
    assert "[redacted]" in stdio["success"]["cleanup"]["stdout_tail"]
    assert stdio["success"]["cleanup"]["stdio_drain_complete"] is True
    assert stdio["inherited_pipe"]["cleanup"]["stopped"] is True
    assert stdio["inherited_pipe"]["cleanup"]["stdio_drain_complete"] is False
    assert stdio["inherited_pipe"]["cleanup"]["stdout_drain_complete"] is False
    assert stdio["inherited_pipe"]["cleanup"]["stderr_drain_complete"] is False
    assert "dummy-token-secret" not in json.dumps(stdio)
    assert SENTINEL not in receipt.read_text(encoding="utf-8-sig")
    assert SENTINEL not in result.stdout
    assert SENTINEL not in result.stderr


def test_isolated_gateway_start_stop_drains_child_stdio_without_runspace_callbacks(tmp_path):
    dummy_repo = tmp_path / "dummy-repo"
    harness = dummy_repo / "harness"
    harness.mkdir(parents=True)
    (harness / "gateway.py").write_text(
        textwrap.dedent(
            """
            import os, pathlib, subprocess, sys, tempfile, time
            home = pathlib.Path(os.environ["FLYWHEEL_HOME"])
            mode = os.environ.get("FW_DUMMY_GATEWAY_MODE", "fail")
            if mode == "success":
                home.mkdir(parents=True, exist_ok=True)
                (home / "gateway.token").write_text("dummy-token-secret", encoding="utf-8")
                print("dummy success stdout dummy-token-secret", flush=True)
                print("dummy success stderr dummy-token-secret", file=sys.stderr, flush=True)
                time.sleep(30)
            elif mode == "inherited":
                home.mkdir(parents=True, exist_ok=True)
                (home / "gateway.token").write_text("dummy-token-secret", encoding="utf-8")
                subprocess.Popen([sys.executable, "-c", "import sys,time; print('descendant stdout dummy-token-secret', flush=True); print('descendant stderr dummy-token-secret', file=sys.stderr, flush=True); time.sleep(20)"], cwd=tempfile.gettempdir())
                print("parent inherited stdout", flush=True)
                print("parent inherited stderr", file=sys.stderr, flush=True)
                sys.exit(9)
            else:
                print("dummy fail stdout", flush=True)
                print("dummy fail stderr", file=sys.stderr, flush=True)
                sys.exit(7)
            """
        ).strip(),
        encoding="utf-8",
    )
    script = tmp_path / "probe.ps1"
    script.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            . {_ps_literal(SUPPORT)}
            function Ensure-Dirs($HomePath, $RunPath) {{
              New-Item -ItemType Directory -Force -Path $HomePath,$RunPath | Out-Null
            }}
            $failHome = {_ps_literal(tmp_path / "fail-home")}
            $failRuns = {_ps_literal(tmp_path / "fail-runs")}
            Ensure-Dirs $failHome $failRuns
            $env:FW_DUMMY_GATEWAY_MODE = 'fail'
            $fail = Start-IsolatedGateway {_ps_literal(sys.executable)} {_ps_literal(dummy_repo)} 1 $failHome $failRuns $false
            $failCleanup = Stop-OwnedGateway $fail '' 'synthetic-device'
            $okHome = {_ps_literal(tmp_path / "ok-home")}
            $okRuns = {_ps_literal(tmp_path / "ok-runs")}
            Ensure-Dirs $okHome $okRuns
            $env:FW_DUMMY_GATEWAY_MODE = 'success'
            $ok = Start-IsolatedGateway {_ps_literal(sys.executable)} {_ps_literal(dummy_repo)} 1 $okHome $okRuns $false
            $okCleanup = Stop-OwnedGateway $ok 'dummy-token-secret' 'synthetic-device'
            $inheritedHome = {_ps_literal(tmp_path / "inherited-home")}
            $inheritedRuns = {_ps_literal(tmp_path / "inherited-runs")}
            Ensure-Dirs $inheritedHome $inheritedRuns
            $env:FW_DUMMY_GATEWAY_MODE = 'inherited'
            $inherited = Start-IsolatedGateway {_ps_literal(sys.executable)} {_ps_literal(dummy_repo)} 1 $inheritedHome $inheritedRuns $false
            $inheritedCleanup = Stop-OwnedGateway $inherited 'dummy-token-secret' 'synthetic-device'
            Remove-Item Env:FW_DUMMY_GATEWAY_MODE -ErrorAction SilentlyContinue
            @{{
              fail = @{{
                alive = $fail.alive
                startup_state = $fail.startup_state
                exit_code = $fail.exit_code
                cleanup = $failCleanup
              }}
              success = @{{
                alive = $ok.alive
                startup_state = $ok.startup_state
                  exit_code = $ok.exit_code
                  cleanup = $okCleanup
                }}
              inherited = @{{
                alive = $inherited.alive
                startup_state = $inherited.startup_state
                exit_code = $inherited.exit_code
                cleanup = $inheritedCleanup
              }}
            }} | ConvertTo-Json -Depth 12
            """
        ).strip(),
        encoding="utf-8",
    )
    started = time.monotonic()
    result = subprocess.run(
        [_shell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=12,
    )
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stderr + result.stdout
    assert elapsed < 6
    proof = json.loads(result.stdout)
    assert proof["fail"]["alive"] is False
    assert proof["fail"]["startup_state"] == "process_exited_before_token"
    assert proof["fail"]["exit_code"] == 7
    assert proof["fail"]["cleanup"]["exit_code"] == 7
    assert "dummy fail stdout" in proof["fail"]["cleanup"]["stdout_tail"]
    assert "dummy fail stderr" in proof["fail"]["cleanup"]["stderr_tail"]
    assert proof["success"]["alive"] is True
    assert proof["success"]["startup_state"] == "running_without_world_probe"
    assert proof["success"]["cleanup"]["stopped"] is True
    assert proof["success"]["cleanup"]["stdio_drain_complete"] is True
    assert "[redacted]" in proof["success"]["cleanup"]["stdout_tail"]
    assert "[redacted]" in proof["success"]["cleanup"]["stderr_tail"]
    assert proof["inherited"]["cleanup"]["stopped"] is True
    assert proof["inherited"]["cleanup"]["stdio_drain_complete"] is False
    assert proof["inherited"]["cleanup"]["stdout_drain_complete"] is False
    assert proof["inherited"]["cleanup"]["stderr_drain_complete"] is False
    assert "dummy-token-secret" not in result.stdout


def test_real_gateway_runner_source_preserves_user_state_and_omits_lan_modes():
    runner = RUNNER.read_text(encoding="utf-8-sig")
    support = SUPPORT.read_text(encoding="utf-8-sig")
    fixture = FIXTURE.read_text(encoding="utf-8-sig")
    combined = "\n".join([runner, support, fixture])

    assert "--no-uninstall" in runner
    assert "pm clear" not in combined
    assert "reverse --remove-all" not in combined
    assert "adb tcpip" not in combined
    assert "adb connect" not in combined
    assert "[string]$GatewayToken" not in runner
    assert "RedirectStandardInput" in support
    assert "Invoke-AdbRunAsInput" in support
    assert "run-as" in support
    assert '"sh", "-c"' not in support
    assert "&&" not in support
    assert "cat >" not in support
    assert "FLYWHEEL_ANDROID_REAL_GATEWAY_TOKEN" not in combined
    assert "FLYWHEEL_ANDROID_REAL_GATEWAY_HANDOFF_RECEIPT_JSON" in fixture
    assert "android_gateway_handoff_test.dart" not in fixture
