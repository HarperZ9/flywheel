"""flywheel-check-mcp as a user gets it: from a built wheel, not the source tree.

The Claude plugin starts the server with `uvx --from flywheel-verify==<v>
flywheel-check-mcp`. The first test installs the wheel with pip into a fresh
virtual environment and runs the console script from a folder with no source
checkout in reach. The second runs the plugin's exact command and arguments
through uv, offline, with the local wheel as the only package source, so nothing
is fetched and the pin has to match the build; it skips on a host without uv.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_writing_portability_distribution import (_install_wheel, _installed_env,
                                                   _rpc, _script)

ROOT = Path(__file__).resolve().parents[1]
MESSAGES = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18"}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
     "params": {"name": "domain_packs", "arguments": {"name": "law"}}},
]


def _assert_serves(responses: list[dict]) -> None:
    assert [r["id"] for r in responses] == [1, 2, 3]
    assert responses[0]["result"]["serverInfo"]["name"] == "flywheel-check"
    tools = responses[1]["result"]["tools"]
    assert [t["name"] for t in tools] == ["check_answer", "domain_packs", "verify_bundle"]
    assert all(t["annotations"]["readOnlyHint"] is True for t in tools)
    law = responses[2]["result"]["structuredContent"]
    assert law["name"] == "law" and "not a legal authority" in law["caution"]


def test_the_installed_command_serves_from_an_isolated_folder(tmp_path):
    env_dir = _install_wheel(tmp_path)
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    env = _installed_env(dict(os.environ, PYTHONPATH=str(ROOT)))
    assert "PYTHONPATH" not in env
    responses = _rpc(_script(env_dir, "flywheel-check-mcp"), MESSAGES, isolated, env=env)
    _assert_serves(responses)
    version = subprocess.run([_script(env_dir, "flywheel-check-mcp"), "--version"],
                             capture_output=True, text=True, cwd=isolated, env=env,
                             check=False)
    assert version.returncode == 0
    assert version.stdout.strip() == f"flywheel-check {responses[0]['result']['serverInfo']['version']}"


@pytest.mark.skipif(shutil.which("uvx") is None, reason="uv is not installed on this host")
def test_the_plugin_command_runs_offline_from_the_wheel(tmp_path):
    """The exact command and arguments in .mcp.json, pin included.

    uv is told to take packages only from a folder holding the local build and
    never to reach the network, so the pinned version resolves only when the
    wheel carries that version, and nothing is fetched.
    """
    wheelhouse = tmp_path / "wheelhouse"
    built = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps",
                            "--no-build-isolation", "--no-index", "-w", str(wheelhouse),
                            str(ROOT)], capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    assert len(list(wheelhouse.glob("flywheel_verify-*.whl"))) == 1
    config = json.loads((ROOT / "plugins" / "flywheel-verify" / ".mcp.json").read_text(
        encoding="utf-8"))["mcpServers"]["check"]
    args = list(config["args"])
    assert args[0] == "--from" and args[1].startswith("flywheel-verify==")
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    env = _installed_env(UV_CACHE_DIR=str(tmp_path / "uv-cache"), UV_NO_CONFIG="1",
                         UV_PYTHON=sys.executable, UV_PYTHON_DOWNLOADS="never",
                         UV_OFFLINE="1", UV_NO_INDEX="1", UV_FIND_LINKS=str(wheelhouse))
    proc = subprocess.run([shutil.which(config["command"]), *args],
                          input="".join(json.dumps(m) + "\n" for m in MESSAGES),
                          capture_output=True, text=True, cwd=isolated, env=env,
                          timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
    _assert_serves([json.loads(line) for line in proc.stdout.splitlines() if line.strip()])
    # The control: the same command with a pin no local wheel carries cannot
    # start, so the success above rests on the pin resolving, not on uv
    # picking up whatever build it found.
    other = [args[0], "flywheel-verify==0.0.1", *args[2:]]
    missed = subprocess.run([shutil.which(config["command"]), *other], input="",
                            capture_output=True, text=True, cwd=isolated, env=env,
                            timeout=120, check=False)
    assert missed.returncode != 0 and not missed.stdout.strip()
