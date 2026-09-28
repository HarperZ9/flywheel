"""Package-launch controls for the endpoint-gate command."""

import json
import subprocess
import sys

import pytest

import harness.cli_entry as cli
from tests.model_endpoint_gate_fixtures import profile, write_profiles


def _no_repo():
    raise FileNotFoundError("no checkout")


def _tail(text: str) -> str:
    return text[-2000:] if text else ""


def _run_checked(label: str, argv: list[str], *, cwd=None, timeout: float):
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        raise AssertionError(
            f"{label} timed out after {timeout}s\nstdout:\n{_tail(stdout)}\nstderr:\n{_tail(stderr)}") from exc
    if result.returncode != 0:
        raise AssertionError(
            f"{label} failed with exit {result.returncode}\nstdout:\n{_tail(result.stdout)}\nstderr:\n{_tail(result.stderr)}")
    return result


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


@pytest.mark.timeout(400)
def test_built_wheel_exposes_endpoint_gate_help_outside_checkout(tmp_path):
    root = cli.Path(__file__).resolve().parents[1]
    wheels, env = tmp_path / "wheels", tmp_path / "env"
    wheels.mkdir()
    _run_checked("build endpoint-gate wheel",
                 [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", str(wheels)],
                 cwd=root, timeout=150)
    _run_checked("create endpoint-gate venv", [sys.executable, "-m", "venv", str(env)], timeout=60)
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    wheel = next(wheels.glob("*.whl"))
    _run_checked("install endpoint-gate wheel",
                 [str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)],
                 timeout=60)
    exe = env / ("Scripts/flywheel.exe" if sys.platform == "win32" else "bin/flywheel")

    root_help = _run_checked("flywheel root help", [str(exe), "--help"], cwd=tmp_path, timeout=20)
    endpoint_help = _run_checked("flywheel endpoint-gate help",
                                 [str(exe), "endpoint-gate", "--help"],
                                 cwd=tmp_path, timeout=20)

    assert root_help.returncode == endpoint_help.returncode == 0
    assert "endpoint-gate" in root_help.stdout
    assert "--profile-id" in endpoint_help.stdout
    assert "--max-generation-calls" in endpoint_help.stdout
    assert "requires a source checkout" not in endpoint_help.stderr
