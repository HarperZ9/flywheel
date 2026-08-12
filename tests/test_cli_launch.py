"""Falsifiers for the standalone gateway launcher (harness/cli_entry.py).

A bare `pip install flywheel-verify` ships harness/ but not scripts/. `flywheel
up` and `flywheel app` must start the gateway by importing harness.gateway
directly, never requiring a source checkout. Passthrough commands with no
checkout must fail with a message, not a traceback. When a checkout IS present
(dev), the launcher must still prefer scripts/run_harness_cli.py. When frozen
(PyInstaller exe), the checkout probe must be skipped entirely.
"""
import harness.cli_entry as cli
import harness.gateway as gw
import pytest
import subprocess
import hashlib, json, sys, venv
import base64
from harness.cross_harness_adapters import CodexCliProposer, DirectCodexAdapter, FlywheelRouterAdapter, _run_process
from harness.cross_harness_executor import SHARED_TOOL_POLICY, execute_cross_harness_manifest
from harness.cross_harness_types import AttemptRequest


def _record(store):
    """A gateway.main stand-in that records its argv and returns 0 (success)."""
    def _fake(argv):
        store["argv"] = argv
        return 0
    return _fake


def _no_repo():
    raise FileNotFoundError("no checkout")


def test_launch_gateway_uses_package_when_no_checkout(monkeypatch):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    rc = cli._launch_gateway(["--port", "8799"])
    assert rc == 0
    assert seen["argv"] == ["--port", "8799"]


def test_launch_gateway_prefers_checkout_when_present(monkeypatch, tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_harness_cli.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setattr(cli, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    monkeypatch.setattr(cli.os, "chdir", lambda p: None)  # no real cwd change
    ran = {}

    def _fake_runpath(path, run_name=None):
        ran["path"] = path
        ran["argv"] = list(cli.sys.argv)
        raise SystemExit(0)

    monkeypatch.setattr(cli.runpy, "run_path", _fake_runpath)
    rc = cli._launch_gateway(["--port", "8799"])
    assert rc == 0
    assert ran["path"].endswith("run_harness_cli.py")
    assert ran["argv"][1:] == ["app", "--port", "8799"]


def test_launch_gateway_frozen_never_consults_the_checkout(monkeypatch, tmp_path):
    # A frozen exe must run the bundled package even when a checkout exists on
    # disk: find_repo_root would succeed here, so passing proves it is skipped.
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_harness_cli.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setattr(cli, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    ran = {"runpy": False}
    monkeypatch.setattr(cli.runpy, "run_path",
                        lambda *a, **k: ran.__setitem__("runpy", True))
    rc = cli._launch_gateway(["--port", "8799"])
    assert rc == 0
    assert seen["argv"] == ["--port", "8799"]
    assert ran["runpy"] is False


def test_app_command_launches_gateway_without_checkout(monkeypatch):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    rc = cli.main(["app", "--port", "8799"])
    assert rc == 0
    assert seen["argv"] == ["--port", "8799"]


def test_app_command_keeps_a_value_that_equals_app(monkeypatch):
    # Only the command token is dropped; a later value spelled "app"
    # (e.g. `--root app`) must survive.
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    rc = cli.main(["app", "--root", "app"])
    assert rc == 0
    assert seen["argv"] == ["--root", "app"]


def test_up_command_launches_gateway_without_checkout(monkeypatch):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    rc = cli.main(["up"])
    assert rc == 0
    # _cmd_up injects the exact default port before delegating to the launcher.
    assert seen["argv"] == ["--port", "8799"]


def test_passthrough_without_checkout_fails_gracefully(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    rc = cli.main(["mcp-health"])
    assert rc == 2
    assert "requires a source checkout" in capsys.readouterr().err


def test_bare_invocation_without_checkout_prints_usage(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    rc = cli.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage: flywheel" in err
    assert "up" in err and "lanes" in err


def test_help_without_checkout_is_a_success(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    rc = cli.main(["--help"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "usage: flywheel" in out
    assert "up" in out and "lanes" in out and "cross-harness-execute" in out


def test_cross_harness_execute_help_uses_packaged_module_without_checkout(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["cross-harness-execute", "--help"])
    assert stopped.value.code == 0
    assert "--runtime-matrix" in capsys.readouterr().out


def test_cross_harness_source_wrapper_exposes_the_same_help_from_any_cwd(tmp_path):
    script = cli.Path(__file__).resolve().parents[1] / "scripts" / "run_cross_harness_execution.py"
    completed = subprocess.run([cli.sys.executable, str(script), "--help"], cwd=tmp_path,
                               capture_output=True, text=True, check=False)
    assert completed.returncode == 0
    assert "--runtime-matrix" in completed.stdout


def test_built_wheel_exposes_root_and_cross_harness_help_outside_checkout(tmp_path):
    root, wheels, env = cli.Path(__file__).resolve().parents[1], tmp_path / "wheels", tmp_path / "env"
    wheels.mkdir()
    built = subprocess.run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "-w", str(wheels)], cwd=root, capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    venv.EnvBuilder(with_pip=True).create(env)
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    installed = subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(next(wheels.glob("*.whl")))], capture_output=True, text=True)
    assert installed.returncode == 0, installed.stderr
    exe = env / ("Scripts/flywheel.exe" if sys.platform == "win32" else "bin/flywheel")
    root_help = subprocess.run([str(exe), "--help"], cwd=tmp_path, capture_output=True, text=True)
    sub_help = subprocess.run([str(exe), "cross-harness-execute", "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert root_help.returncode == sub_help.returncode == 0 and "cross-harness-execute" in root_help.stdout and "--runtime-matrix" in sub_help.stdout


def _attempt(tmp_path, role="codex_harness", adapter="codex_cli_json/v1"):
    return AttemptRequest("run", "spark", "set", "agt-001-task", "prompt", "a" * 64, role, role.split("_")[0], adapter, "spark", tmp_path, "b" * 64, {}, SHARED_TOOL_POLICY, "c" * 64, 1, "cold_declared", 3, tmp_path)


@pytest.mark.parametrize("command", ['bash -c "echo bad > x"', "sh -c 'echo bad > x'", 'dash -eu -c "echo bad > x"', 'zsh --no-rcs -fc "echo bad > x"', 'cmd /c "echo bad > x"', 'cmd.exe /d /v:on /c "echo bad > x"', 'C:\\Windows\\System32\\cmd.exe /s /c "echo bad > x"', 'powershell.exe -NoProfile -Command "echo bad > x"', 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -Command "echo bad > x"', 'pwsh -NonInteractive -c "echo bad > x"'])
def test_quoted_executable_wrappers_report_shell_and_write(command, tmp_path):
    process = type("Outcome", (), {"returncode": 0, "stdout": json.dumps({"type": "command_execution", "command": command}), "stderr": "", "output_text": "", "elapsed_ms": 1, "timed_out": False, "malformed_output": False})()
    result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_attempt(tmp_path))
    assert result.observed_capabilities == ["shell", "write"] and result.policy_violations == ["exec_not_allowed", "write_not_allowed"]


@pytest.mark.parametrize("command", ['bash -c "python -c \'print(1 > 0)\'"', 'pwsh -Command "Write-Output \'1 > 0\'"', 'powershell -Co "Write-Output \'1 > 0\'"', 'powershell /Co "Write-Output \'1 > 0\'"'])
def test_quoted_wrapper_comparisons_are_not_writes(command, tmp_path):
    process = type("Outcome", (), {"returncode": 0, "stdout": json.dumps({"type": "command_execution", "command": command}), "stderr": "", "output_text": "", "elapsed_ms": 1, "timed_out": False, "malformed_output": False})()
    result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_attempt(tmp_path))
    assert "write" not in result.observed_capabilities


@pytest.mark.parametrize("command", ['bash -c "printf \\">\\""', 'powershell -Command "Write-Output `\">`\""', 'cmd /c "echo ^> out"'])
def test_wrapper_escaped_redirect_data_is_not_write(command, tmp_path):
    process = type("Outcome", (), {"returncode": 0, "stdout": json.dumps({"type": "command_execution", "command": command}), "stderr": "", "output_text": "", "elapsed_ms": 1, "timed_out": False, "malformed_output": False})()
    result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_attempt(tmp_path))
    assert "write" not in result.observed_capabilities


def test_encoded_powershell_and_cmd_keep_commands_are_audited(tmp_path):
    encoded = base64.b64encode("echo bad > x".encode("utf-16le")).decode()
    for command in (f"pwsh -EncodedCommand {encoded}", f"powershell -EC {encoded}", f"powershell /EC {encoded}", f"powershell /E {encoded}", f"powershell -En {encoded}", f"powershell /En {encoded}", f"powershell /Enc {encoded}", f"powershell -Enco {encoded}", f"powershell /Encode {encoded}", f"powershell -Encoded {encoded}", f"powershell /Encoded {encoded}", f"powershell -EncodedC {encoded}", f"powershell -EncodedCom {encoded}",
                    'powershell -Co "echo bad > x"', 'powershell /Co "echo bad > x"', 'powershell -Com "echo bad > x"', 'powershell -Comm "echo bad > x"', 'cmd.exe /d /k "echo bad > x"'):
        process = type("Outcome", (), {"returncode": 0, "stdout": json.dumps({"type": "command_execution", "command": command}), "stderr": "", "output_text": "", "elapsed_ms": 1, "timed_out": False, "malformed_output": False})()
        result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_attempt(tmp_path))
        assert "write_not_allowed" in result.policy_violations


@pytest.mark.parametrize("command", ['cmd.exe /d /c"echo bad > x"', 'cmd.exe /s /k"echo bad > x"'])
def test_cmd_attached_command_switch_is_audited(command, tmp_path):
    process = type("Outcome", (), {"returncode": 0, "stdout": json.dumps({"type": "command_execution", "command": command}), "stderr": "", "output_text": "", "elapsed_ms": 1, "timed_out": False, "malformed_output": False})()
    result = DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_attempt(tmp_path))
    assert "write_not_allowed" in result.policy_violations


def test_real_child_streams_are_bounded_without_output_stage(tmp_path):
    code = "import sys;sys.stdout.buffer.write(b'x'*(2<<20));sys.stderr.buffer.write(b'y'*(2<<20))"
    result = _run_process([sys.executable, "-c", code], cwd=tmp_path, stdin_text="", timeout_seconds=3)
    assert result.malformed_output and max(map(len, (result.stdout, result.stderr))) <= (1 << 20)
    assert not list(tmp_path.glob(".cross-harness-stage-*"))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows suspended-launch boundary")
def test_windows_child_cannot_spawn_before_job_assignment(tmp_path, monkeypatch):
    import harness.cross_harness_process as process
    import time
    marker = tmp_path / "escaped"
    grandchild = f"import pathlib,time;time.sleep(.7);pathlib.Path({str(marker)!r}).write_text('bad')"
    child = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',sys.argv[1]],creationflags=8);time.sleep(30)"
    original = process._windows_job
    def delayed(proc): time.sleep(.3); return original(proc)
    monkeypatch.setattr(process, "_windows_job", delayed)
    result = _run_process([sys.executable, "-c", child, grandchild], cwd=tmp_path, stdin_text="", timeout_seconds=.55)
    time.sleep(.9)
    assert result.timed_out and not marker.exists()


def test_nonfinite_provider_json_still_seals_executor_receipt(tmp_path):
    source = tmp_path / "source"; source.mkdir(); prompt = "prompt"
    task = {"task_id": "agt-001-task", "raw_prompt": prompt, "raw_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "input_sha256s": {}, "required_inputs": [], "expected_artifacts": [], "oracle": {}}
    manifest = {"task_set_id": "set", "task_rows": [task], "provider_specs": [{"provider_role": "codex_harness", "harness_id": "codex", "adapter_id": "codex_cli_json/v1", "target_model": "spark"}]}
    runtime = {"runtime_rows": [{"provider_role": "codex_harness", "focused_run_ready": True, "blocking_gates": []}]}
    process = type("Outcome", (), {"returncode": 0, "stdout": '{"value":NaN}\n', "stderr": "", "output_text": "", "elapsed_ms": 1, "timed_out": False, "malformed_output": False})()
    run = execute_cross_harness_manifest(manifest, runtime, {"codex_harness": DirectCodexAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")}, artifact_root=tmp_path / "artifacts", source_root=source, run_id="run", phase="spark", selectors=["agt-001"], roles=["codex_harness"], repetitions=1)
    assert (run["rows"][0]["execution_state"], run["rows"][0]["receipt_state"]) == ("malformed", "verified")


@pytest.mark.parametrize("rc", [0, 7])
def test_inner_invalid_utf8_is_malformed_through_full_adapter(tmp_path, rc):
    process = _run_process([sys.executable, "-c", f"import sys;sys.stdout.buffer.write(b'\\xff');sys.exit({rc})"], cwd=tmp_path, stdin_text="", timeout_seconds=2)
    proposer = CodexCliProposer("spark", workspace=tmp_path, artifact_dir=tmp_path, timeout_seconds=2, runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd")
    with pytest.raises(Exception) as caught: proposer.generate("p", seed=0, temperature=0, max_new_tokens=1)
    assert type(caught.value).__name__ == "MalformedProviderOutput"
    result = FlywheelRouterAdapter(runner=lambda *a, **k: process, executable_resolver=lambda: "codex.cmd").execute(_attempt(tmp_path, "flywheel_harness", "flywheel_router/v1"))
    assert result.execution_state == "malformed" and result.failure_class == "malformed_provider_output"


def test_lanes_probe_flag_is_forwarded_to_roster(monkeypatch, capsys):
    calls = []
    roster = {"n_lanes": 0, "by_status": {}, "lanes": []}
    monkeypatch.setattr(
        "harness.lanes.lane_roster",
        lambda **kwargs: calls.append(kwargs) or roster,
    )
    monkeypatch.setattr("harness.lanes.lane_report", lambda value: "empty")
    assert cli._dispatch_umbrella("lanes", ["--probe"]) == 0
    assert calls == [{"probe": True}]
