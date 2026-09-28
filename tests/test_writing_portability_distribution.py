"""Installed MCP commands and plugin templates for portable writing tools."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _installed_env(ambient: dict[str, str] | None = None, **overrides: str) -> dict[str, str]:
    env = dict(ambient or os.environ)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    env.update(overrides)
    return env


def _run(args: list[str], cwd: Path = ROOT, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env or _installed_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _venv_python(env_dir: Path) -> Path:
    if os.name == "nt":
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def _venv_scripts(env_dir: Path) -> Path:
    if os.name == "nt":
        return env_dir / "Scripts"
    return env_dir / "bin"


def _script(env_dir: Path, name: str) -> str:
    path = shutil.which(name, path=str(_venv_scripts(env_dir)))
    assert path is not None, f"missing installed script {name}"
    return path


def _install_wheel(tmp_path: Path) -> Path:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    built = _run([
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "--no-build-isolation",
        "--no-index",
        "-w",
        str(wheelhouse),
        str(ROOT),
    ])
    assert built.returncode == 0, built.stderr

    env_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(env_dir)
    py = _venv_python(env_dir)
    installed = _run([
        str(py),
        "-m",
        "pip",
        "install",
        "--no-index",
        "--find-links",
        str(wheelhouse),
        "flywheel-verify",
    ])
    assert installed.returncode == 0, installed.stderr
    return env_dir


def _rpc(command: str, messages: list[dict], cwd: Path, *, env: dict[str, str] | None = None) -> list[dict]:
    proc = subprocess.Popen(
        [command],
        cwd=cwd,
        env=env or _installed_env(),
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None
    for message in messages:
        proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.close()
    stdout = proc.stdout.read() if proc.stdout is not None else ""
    stderr = proc.stderr.read() if proc.stderr is not None else ""
    code = proc.wait(timeout=10)
    assert code == 0, stderr
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _poison_source_tree(root: Path) -> Path:
    package = root / "harness" / "writing_lint"
    package.mkdir(parents=True)
    (root / "harness" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "mcp.py").write_text(
        "raise RuntimeError('poison source shadowed installed package')\n",
        encoding="utf-8",
    )
    return root


def test_installed_lint_mcp_command_runs_from_isolated_cwd(tmp_path: Path) -> None:
    env_dir = _install_wheel(tmp_path)
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    poison = _poison_source_tree(tmp_path / "poison-source")
    dirty_ambient = dict(os.environ, PYTHONPATH=str(poison), PYTHONHOME=str(tmp_path / "fake-python-home"))
    env = _installed_env(dirty_ambient)
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    responses = _rpc(_script(env_dir, "flywheel-writing-lint-mcp"), [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "writing.lint", "arguments": {
             "profile": "research",
             "text": "We utilize a seamless tool.",
         }}},
    ], isolated, env=env)

    assert responses[0]["result"]["serverInfo"]["name"] == "writing-lint"
    assert {tool["name"] for tool in responses[1]["result"]["tools"]} == {
        "writing.profiles", "writing.lint", "writing.delta"}
    payload = json.loads(responses[2]["result"]["content"][0]["text"])
    assert "banned_word" in payload["hard"]
    assert payload["violations"]["banned_word"] >= 1
    assert "does_not_prove" in payload


def test_installed_workspace_mcp_command_requires_home_and_keeps_approval_out_of_band(tmp_path: Path) -> None:
    env_dir = _install_wheel(tmp_path)
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    command = _script(env_dir, "flywheel-writing-workspace-mcp")
    no_home_env = _installed_env()
    no_home_env.pop("FLYWHEEL_HOME", None)
    refused = _run([command], isolated, env=no_home_env)
    assert refused.returncode == 64
    assert "FLYWHEEL_HOME" in refused.stderr
    placeholder = _run([command], isolated, env=dict(no_home_env, FLYWHEEL_HOME="${FLYWHEEL_HOME}"))
    assert placeholder.returncode == 64
    assert "operator-owned" in placeholder.stderr

    home = tmp_path / "owner-home"
    with_home_env = dict(no_home_env, FLYWHEEL_HOME=str(home))
    outside = tmp_path / "outside-home"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    responses = _rpc(command, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "writing.status", "arguments": {
             "home": str(outside),
         }}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "writing.status", "arguments": {
             "home": str(home),
         }}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "writing.proposal_approve", "arguments": {
             "proposal_ref": "prp_" + "a" * 32,
         }}},
    ], isolated, env=with_home_env)

    assert responses[0]["result"]["serverInfo"]["name"] == "writing-workspace"
    assert "writing.proposal_commit" in {tool["name"] for tool in responses[1]["result"]["tools"]}
    wrong_home = json.loads(responses[2]["result"]["content"][0]["text"])
    assert wrong_home["error"]["code"] == "HOME_MISMATCH"
    assert sentinel.read_text(encoding="utf-8") == "untouched"
    assert not (outside / "owner.ref").exists()
    assert not (outside / "state").exists()
    matched_home = json.loads(responses[3]["result"]["content"][0]["text"])
    assert matched_home["schema"] == "flywheel.writing-status/v1"
    payload = json.loads(responses[4]["result"]["content"][0]["text"])
    assert payload["error"]["code"] == "APPROVAL_UNAVAILABLE"
    assert "grant_ref" not in payload


def test_legacy_module_route_still_accepts_per_call_home(tmp_path: Path) -> None:
    from harness import writing_mcp

    legacy = tmp_path / "legacy-home"
    response = writing_mcp.handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "writing.status", "arguments": {
            "home": str(legacy),
        }},
    })

    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["schema"] == "flywheel.writing-status/v1"
    assert (legacy / "owner.ref").is_file()


def test_portable_writing_plugins_use_installed_commands_without_source_cwd() -> None:
    cases = {
        "flywheel-writing-lint": "flywheel-writing-lint-mcp",
        "flywheel-writing-workspace": "flywheel-writing-workspace-mcp",
    }
    for plugin_name, command in cases.items():
        root = ROOT / "plugins" / plugin_name
        manifest = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
        assert manifest["name"] == plugin_name
        assert manifest["mcpServers"] == "./.mcp.json"
        server = mcp["mcpServers"][plugin_name]
        assert server["command"] == command
        assert server.get("args", []) == []
        assert "cwd" not in server
        assert str(ROOT).replace("\\", "/") not in json.dumps(server).replace("\\", "/")
    workspace_server = json.loads(
        (ROOT / "plugins" / "flywheel-writing-workspace" / ".mcp.json").read_text(encoding="utf-8")
    )["mcpServers"]["flywheel-writing-workspace"]
    assert workspace_server["env"]["FLYWHEEL_HOME"] == "${FLYWHEEL_HOME}"
