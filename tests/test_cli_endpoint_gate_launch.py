"""Package-launch controls for the endpoint-gate command."""

import json
import subprocess
import sys
import venv

import pytest

import harness.cli_entry as cli
from tests.model_endpoint_gate_fixtures import profile, write_profiles


def _no_repo():
    raise FileNotFoundError("no checkout")


def test_endpoint_gate_help_uses_packaged_module_without_checkout(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["endpoint-gate", "--help"])
    assert stopped.value.code == 0
    out = capsys.readouterr().out
    assert "--profile-id" in out and "--max-generation-calls" in out


def test_endpoint_gate_budget_failure_runs_packaged_without_checkout(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    profile_artifact = write_profiles(tmp_path, [profile()])
    out = tmp_path / "gate.json"
    store = tmp_path / "store"

    rc = cli.main([
        "endpoint-gate", "--profile-artifact", str(profile_artifact),
        "--profile-id", "serve-14b", "--max-generation-calls", "0",
        "--strict-exit", "--out", str(out), "--store-root", str(store),
    ])

    captured = capsys.readouterr()
    assert rc == 1
    assert "requires a source checkout" not in captured.err
    report = json.loads(captured.out)
    assert report["schema"] == "harness.model-endpoint-gate/v1"
    assert report["failure_class"] == "generation_call_budget_exceeded"
    assert report["verdict"] == "MODEL_ENDPOINT_GATE_FAIL"
    assert report["rows"] == []
    assert report["generation_plan"]["admitted"] is False
    assert out.exists()
    assert report["store_outputs"][0]["schema"] == "harness.receipt/v1"


def test_built_wheel_exposes_endpoint_gate_help_outside_checkout(tmp_path):
    root = cli.Path(__file__).resolve().parents[1]
    wheels, env = tmp_path / "wheels", tmp_path / "env"
    wheels.mkdir()
    built = subprocess.run([sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
                            "-w", str(wheels)], cwd=root, capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    venv.EnvBuilder(with_pip=True).create(env)
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    wheel = next(wheels.glob("*.whl"))
    installed = subprocess.run([str(python), "-m", "pip", "install", "--no-deps",
                                "--no-index", str(wheel)], capture_output=True, text=True)
    assert installed.returncode == 0, installed.stderr
    exe = env / ("Scripts/flywheel.exe" if sys.platform == "win32" else "bin/flywheel")

    root_help = subprocess.run([str(exe), "--help"], cwd=tmp_path, capture_output=True, text=True)
    endpoint_help = subprocess.run([str(exe), "endpoint-gate", "--help"],
                                   cwd=tmp_path, capture_output=True, text=True)

    assert root_help.returncode == endpoint_help.returncode == 0
    assert "endpoint-gate" in root_help.stdout
    assert "--profile-id" in endpoint_help.stdout
    assert "--max-generation-calls" in endpoint_help.stdout
    assert "requires a source checkout" not in endpoint_help.stderr
