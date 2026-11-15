"""Shell children (``run``, ``test_cmd``, ``check``, bisect) get an environment allowlist.

Falsifier for the 0.3.0 audit probe P6: a fake ``OPENAI_API_KEY`` in the server's
environment printed from inside ``run``, so a model with exec could read every
provider key into the ledger it hands back. The children now see the platform
base, a fixed set of toolchain variables, and the names the launch lists in
``RELAY_CHILD_ENV``. Also here: the launch-only keys and the protected write
names for agent-CLI configuration folders.
"""
import os
import sys

import pytest

from relay.bisect import _default_runner
from relay.local_loop import _run_acceptance
from relay.local_session import SessionLedger
from relay.local_tools import ToolExecutor, ToolGate
from relay.mcp_grants import LAUNCH_ONLY_KEYS
from relay.mcp_paths import GuardedExecutor, ProtectedPaths
from relay.remote_state import resolved_env

FAKE = "sk-fake-planted-shell-key-0077"
PRINT = (f'"{sys.executable}" -c "import os;'
         "print('KEY=' + os.environ.get('OPENAI_API_KEY', 'ABSENT'));"
         "print('VENV=' + os.environ.get('VIRTUAL_ENV', 'ABSENT'));"
         "print('EXTRA=' + os.environ.get('RELAY_TEST_EXTRA', 'ABSENT'))\"")
FAILS_IF_KEY = (f'"{sys.executable}" -c "import os,sys;'
                "sys.exit(1 if 'OPENAI_API_KEY' in os.environ else 0)\"")


@pytest.fixture(autouse=True)
def planted(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE)
    monkeypatch.setenv("VIRTUAL_ENV", "venv-kept")
    monkeypatch.setenv("RELAY_TEST_EXTRA", "extra-kept")
    monkeypatch.delenv("RELAY_CHILD_ENV", raising=False)


def _run(tmp_path, cmd):
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True, allow_exec=True))
    res = ex.execute("run", {"cmd": cmd})
    return res.output


def test_run_cannot_see_a_fake_key(tmp_path):
    out = _run(tmp_path, PRINT)
    assert "KEY=ABSENT" in out and FAKE not in out


def test_run_keeps_toolchain_variables_and_named_ones(tmp_path, monkeypatch):
    assert "VENV=venv-kept" in _run(tmp_path, PRINT)
    assert "EXTRA=ABSENT" in _run(tmp_path, PRINT)
    monkeypatch.setenv("RELAY_CHILD_ENV", "RELAY_TEST_EXTRA, OTHER")
    assert "EXTRA=extra-kept" in _run(tmp_path, PRINT)


def test_check_cannot_see_a_fake_key(tmp_path):
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True, allow_exec=True))
    ledger = SessionLedger()
    assert _run_acceptance(FAILS_IF_KEY, ex, ledger) is True
    assert FAKE not in ledger.to_jsonl()


def test_bisect_check_cannot_see_a_fake_key(tmp_path):
    ok, out = _default_runner(FAILS_IF_KEY, str(tmp_path))
    assert ok is True and FAKE not in out


@pytest.mark.skipif(os.name != "nt", reason="cmd.exe searches the working folder on Windows")
def test_run_does_not_pick_a_program_from_the_root_by_bare_name(tmp_path, monkeypatch):
    # Without the variable in the server's own environment, cmd.exe looks in
    # the working folder first; the child's environment must set it.
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    marker = tmp_path / "PLANTED-RAN"
    (tmp_path / "whoami.cmd").write_text(f'@echo off\r\necho x> "{marker}"\r\n',
                                          encoding="utf-8", newline="")
    _run(tmp_path, "whoami")
    assert not marker.exists()


@pytest.mark.parametrize("key", ["RELAY_CHILD_ENV", "RELAY_ALLOW_EXEC_CLI",
                                 "RELAY_CLAUDE_CLI", "RELAY_CODEX_CLI"])
def test_child_and_cli_settings_never_come_from_the_env_file(tmp_path, key):
    assert key in LAUNCH_ONLY_KEYS
    env_file = tmp_path / ".env"
    env_file.write_text(f"{key}=planted\n", encoding="utf-8")
    resolved, _ = resolved_env(env={}, env_file=str(env_file))
    assert key not in resolved


@pytest.mark.parametrize("rel", [".claude/settings.json", ".CLAUDE/settings.local.json",
                                 ".codex/config.toml", ".cursor/mcp.json",
                                 ".vscode/tasks.json", ".gemini/settings.json",
                                 ".agents/skills/x/SKILL.md", ".mcp.json", "sub/.claude/x.json"])
def test_run_file_tools_refuse_agent_cli_configuration(tmp_path, rel):
    ex = GuardedExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True),
                         protected=ProtectedPaths())
    res = ex.execute("write_file", {"path": rel, "content": "{}"})
    assert res.ok is False and "[gate]" in res.output
    assert not (tmp_path / rel).exists()


def test_ordinary_files_are_still_writable(tmp_path):
    ex = GuardedExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True),
                         protected=ProtectedPaths())
    assert ex.execute("write_file", {"path": "src/claude.py", "content": "x"}).ok is True
