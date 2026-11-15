"""The plugin's hook command, run the way Codex runs it on Windows.

Codex (codex-rs/hooks/src/engine/discovery.rs, read at tags rust-v0.144.6,
rust-v0.159.2 and rust-v0.159.3) replaces ${PLUGIN_ROOT}, ${CLAUDE_PLUGIN_ROOT},
${PLUGIN_DATA} and ${CLAUDE_PLUGIN_DATA} in a plugin hook's command text before
it starts a shell, and sets the same names in the environment. From rust-v0.145.0
(openai/codex #33926, "Fix quoted hook commands on Windows") command_runner.rs
runs %COMSPEC% /C "<command>" as a raw argument, which is cmd.exe unless COMSPEC
names another shell. Before that, including the rust-v0.144 patch line, it passed
the command through normal argument quoting, which escapes each inner quote as
\". A limit test below pins that the shipped command does not run under that
older launch, so the documented minimum of Codex 0.145.0 stays true.
So the shell never sees ${CLAUDE_PLUGIN_ROOT}, and PowerShell's reading of that
text as a PowerShell variable does not apply.

These tests run the shipped command, word for word, under cmd.exe, Windows
PowerShell and pwsh, from a plugin folder whose path has a space. A python3.cmd
shim on PATH points python3 at the test interpreter, because a CI runner may
have no python3 on PATH. A control shows that the same command fails when the
text is left unreplaced, so a pass is not vacuous.

This does not show that Codex fires the hook in a live session: that needs a
model turn.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOKS = ROOT / "claude-plugin" / "hooks" / "hooks.json"
SUBSTITUTED = ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "PLUGIN_DATA", "CLAUDE_PLUGIN_DATA")
PATCH = ("*** Begin Patch\n*** Update File: docs/guide.md\n@@ intro\n Upgrade with care.\n"
         "-Version 2.3 might break old plugins.\n+Version 2.3 will break old plugins.\n"
         "*** End Patch")
EVENT = json.dumps({"hook_event_name": "PostToolUse", "session_id": "s", "cwd": "C:/w",
                    "tool_name": "apply_patch", "tool_input": {"command": PATCH}}).encode()
windows_only = pytest.mark.skipif(os.name != "nt", reason="Codex's cmd.exe launcher is Windows only")


def _command():
    return json.loads(HOOKS.read_text("utf-8"))["hooks"]["PostToolUse"][0]["hooks"][0]["command"]


def test_the_command_uses_only_names_codex_replaces_and_quotes_the_path():
    command = _command()
    assert re.findall(r"\$\{([A-Z_]+)\}", command) == ["CLAUDE_PLUGIN_ROOT"]
    assert set(re.findall(r"\$\{([A-Z_]+)\}", command)) <= set(SUBSTITUTED)
    assert '"${CLAUDE_PLUGIN_ROOT}/server/edit_hook.py"' in command
    # No syntax that only one shell understands.
    for token in ("$env:", "%", "'", "`", "&&", "||", ";", "|"):
        assert token not in command, token


@pytest.fixture
def plugin(tmp_path):
    root = tmp_path / "plugin root" / "articulate-writing"
    (root / "server").mkdir(parents=True)
    shutil.copy2(ROOT / "claude-plugin" / "server" / "edit_hook.py", root / "server")
    shutil.copytree(ROOT / "src" / "articulate", root / "src" / "articulate",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shims = tmp_path / "shims"
    shims.mkdir()
    (shims / "python3.cmd").write_text(f'@"{sys.executable}" %*\r\n', encoding="ascii")
    env = dict(os.environ)
    env["PATH"] = str(shims) + os.pathsep + env.get("PATH", "")
    for name in SUBSTITUTED:
        env[name] = str(root) if "ROOT" in name else str(tmp_path / "data")
    return root, env


def _replace(command, env):
    for name in SUBSTITUTED:
        command = command.replace("${%s}" % name, env[name])
    return command


def _context(argv, env):
    result = subprocess.run(argv, input=EVENT, capture_output=True, env=env, timeout=120)
    try:
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError, TypeError):
        return None


def _shells(command):
    comspec = os.environ.get("COMSPEC", "cmd.exe")
    shells = {"cmd": comspec + ' /C "' + command + '"'}
    for name in ("powershell.exe", "pwsh"):
        if shutil.which(name):
            shells[name] = [name, "-NoProfile", "-NonInteractive", "-Command", command]
    return shells


@windows_only
def test_codex_cmd_launch_with_the_root_replaced_returns_advice(plugin):
    root, env = plugin
    command = _replace(_command(), env)
    text = _context(_shells(command)["cmd"], env)
    assert text is not None and "guide.md" in text


@windows_only
@pytest.mark.parametrize("shell", ["powershell.exe", "pwsh"])
def test_powershell_launch_with_the_root_replaced_returns_advice(plugin, shell):
    root, env = plugin
    shells = _shells(_replace(_command(), env))
    if shell not in shells:
        pytest.skip(f"{shell} is not installed")
    text = _context(shells[shell], env)
    assert text is not None and "guide.md" in text


@windows_only
def test_control_the_unreplaced_command_fails_under_cmd_and_powershell(plugin):
    root, env = plugin
    shells = _shells(_command())
    for name, argv in shells.items():
        assert _context(argv, env) is None, name


@windows_only
def test_limit_codex_before_0_145_escapes_the_quotes_and_the_hook_does_not_run(plugin):
    # rust-v0.144.6: Command::new(COMSPEC).arg("/C").arg(command). Rust quotes that
    # argument with the same rules as subprocess.list2cmdline. docs/claude-plugin.md
    # names Codex 0.145.0 as the Windows minimum because of this.
    root, env = plugin
    comspec = os.environ.get("COMSPEC", "cmd.exe")
    argv = subprocess.list2cmdline([comspec, "/C", _replace(_command(), env)])
    assert '\\"' in argv
    assert _context(argv, env) is None
