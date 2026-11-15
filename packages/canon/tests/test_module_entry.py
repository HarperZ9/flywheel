from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = str(Path(__file__).resolve().parents[1] / "src")
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}


@pytest.mark.parametrize("module", ["canon", "canon.cli"])
def test_module_entry_serves_mcp_initialize(module: str) -> None:
    # Catches: canon.cli losing its __main__ guard, so "python -m canon.cli mcp" (the form MCP
    # host configs use) exits 0 without reading stdin and the host reports "Connection closed".
    env = dict(os.environ, PYTHONPATH=SRC + os.pathsep + os.environ.get("PYTHONPATH", ""))
    proc = subprocess.run([sys.executable, "-m", module, "mcp"], input=json.dumps(INIT) + "\n",
                          capture_output=True, text=True, timeout=60, env=env)
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, f"no MCP response from python -m {module} mcp; stderr: {proc.stderr[-400:]}"
    reply = json.loads(lines[0])
    assert reply["id"] == 1
    assert reply["result"]["serverInfo"]["name"] == "canon"


def _run_module(module: str, *args: str) -> subprocess.CompletedProcess:
    # An initialize request waits on stdin, so a module that serves instead of
    # parsing its arguments answers it, and the answer shows up in stdout.
    env = dict(os.environ, PYTHONPATH=SRC + os.pathsep + os.environ.get("PYTHONPATH", ""))
    return subprocess.run([sys.executable, "-m", module, *args], input=json.dumps(INIT) + "\n",
                          capture_output=True, text=True, timeout=60, env=env)


@pytest.mark.parametrize("module", ["canon", "canon.cli"])
def test_python_m_canon_prints_the_version(module: str) -> None:
    import canon

    proc = _run_module(module, "--version")
    assert proc.returncode == 0, proc.stderr[-400:]
    assert proc.stdout == f"canon {canon.__version__}\n"


@pytest.mark.parametrize("module", ["canon", "canon.cli"])
def test_python_m_canon_prints_the_help_without_serving(module: str) -> None:
    proc = _run_module(module, "--help")
    assert proc.returncode == 0, proc.stderr[-400:]
    assert proc.stdout.startswith("usage: canon ")
    assert "placeholder" not in proc.stdout
    assert "serve the read-only record tools over MCP on stdio" in proc.stdout
    assert '"jsonrpc"' not in proc.stdout


SERVERS = [("canon.local_mcp", "canon"), ("canon.context_mcp", "canon-context")]


@pytest.mark.parametrize(("module", "name"), SERVERS)
def test_server_module_prints_its_version_without_serving(module: str, name: str) -> None:
    import canon

    proc = _run_module(module, "--version")
    assert proc.returncode == 0, proc.stderr[-400:]
    assert proc.stdout == f"{name} {canon.__version__}\n"


@pytest.mark.parametrize(("module", "name"), SERVERS)
def test_server_module_prints_help_without_serving(module: str, name: str) -> None:
    proc = _run_module(module, "--help")
    assert proc.returncode == 0, proc.stderr[-400:]
    assert proc.stdout.startswith(f"usage: python -m {module}")
    assert '"jsonrpc"' not in proc.stdout


@pytest.mark.parametrize(("module", "name"), SERVERS)
def test_server_module_refuses_an_unknown_argument(module: str, name: str) -> None:
    proc = _run_module(module, "--bogus")
    assert proc.returncode == 2
    assert "unrecognized arguments: --bogus" in proc.stderr
    assert '"jsonrpc"' not in proc.stdout


@pytest.mark.parametrize(("module", "name"), SERVERS)
def test_server_module_with_no_arguments_serves(module: str, name: str) -> None:
    proc = _run_module(module)
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, f"no MCP response from python -m {module}; stderr: {proc.stderr[-400:]}"
    assert json.loads(lines[0])["result"]["serverInfo"]["name"] == name
