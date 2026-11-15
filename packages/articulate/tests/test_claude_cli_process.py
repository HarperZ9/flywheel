"""Real processes through claude_cli: stand-in shims, planted files, a timeout.

Each stand-in writes back what it received, so a test can check that the prompt
file, the fixed flags and the document arrive intact. No test here reaches a
model. The Windows tests go through cmd.exe and run in the windows-latest CI job.
"""
import ast
import os
import shutil
import stat
import string
import subprocess
import sys
import time

import pytest

from articulate import claude_cli

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_cli_proc")
_WINDOWS = os.name == "nt"
_ECHO = ("import sys\na = sys.argv[1:]\n"
         "p = open(a[a.index('--append-system-prompt-file') + 1], encoding='utf-8').read()\n"
         "sys.stdout.write(repr(a[a.index('--setting-sources'):]) + '|' + p + '|' + sys.stdin.read())\n")
_WHERE = "import os, sys\nsys.stdout.write(repr((os.getcwd(), os.listdir('.'))))\n"
_SLEEP = "import time\ntime.sleep(30)\n"
_FLAGS = ["--setting-sources", "user", "--strict-mcp-config", "--tools", ""]
# npm's cmd-shim template for a package bin, as `npm install -g` writes it. With
# no node.exe beside the shim, it runs "node" by bare name.
_NPM_SHIM = ("@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\n"
             "SETLOCAL\r\nCALL :find_dp0\r\n\r\nIF EXIST \"%dp0%\\node.exe\" (\r\n"
             "  SET \"_prog=%dp0%\\node.exe\"\r\n) ELSE (\r\n  SET \"_prog=node\"\r\n"
             "  SET PATHEXT=%PATHEXT:;.JS;=;%\r\n)\r\n\r\n"
             "endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & \"%_prog%\"  "
             "\"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\cli.js\" %*\r\n")


@pytest.fixture()
def work():
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


def _write(path, text, newline=None):
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)
    return path


def _stand_in(folder, script, name="claude"):
    """A claude stand-in that runs `script` under this Python, as a child."""
    os.makedirs(folder, exist_ok=True)
    body = _write(os.path.join(folder, "body.py"), script)
    if _WINDOWS:
        return _write(os.path.join(folder, name + ".cmd"),
                      f'@echo off\r\n"{sys.executable}" "{body}" %*\r\n', newline="")
    # Not exec: the shell stays the parent, so a timeout has a grandchild to stop.
    shim = _write(os.path.join(folder, name), f'#!/bin/sh\n"{sys.executable}" "{body}" "$@"\necho\n')
    os.chmod(shim, os.stat(shim).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return shim


def _decoy(folder):
    """A file named like the CLI that must never be picked or run."""
    os.makedirs(folder, exist_ok=True)
    name = "claude.cmd" if _WINDOWS else "claude"
    path = _write(os.path.join(folder, name), "@echo PLANTED\r\n" if _WINDOWS else "#!/bin/sh\necho PLANTED\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


def test_a_claude_planted_in_the_current_directory_never_wins(work, monkeypatch):
    # Windows searches the current directory ahead of PATH unless
    # NoDefaultCurrentDirectoryInExePath is set, and Windows does not set it.
    repo = os.path.join(work, "repo")
    _decoy(repo)
    real = _stand_in(os.path.join(work, "bin"), _ECHO)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.delenv(claude_cli.ENV_VAR, raising=False)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("PATH", os.pathsep.join([".", "", os.path.dirname(real)]))
    assert os.path.normcase(claude_cli.resolve()) == os.path.normcase(real)
    r = claude_cli.run("the prompt", "the document", timeout=60)
    assert "PLANTED" not in r.stdout
    assert r.stdout.rstrip("\n").endswith("|the prompt|the document")
    monkeypatch.setenv("PATH", os.pathsep.join([".", ""]))
    with pytest.raises(claude_cli.ClaudeUnavailable):
        claude_cli.resolve()


def test_a_stand_in_receives_the_long_prompt_the_flags_and_the_document(monkeypatch, work):
    cli = _stand_in(os.path.join(work, "bin"), _ECHO)
    monkeypatch.setenv(claude_cli.ENV_VAR, cli)
    prompt = 'one\ntwo "three" %PATH% & four ^ | < > !\n' + "x" * 40000
    r = claude_cli.run(prompt, "the document", timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.rstrip("\n") == repr(_FLAGS) + "|" + prompt + "|the document"


def test_the_cli_never_starts_in_the_callers_folder(work, monkeypatch):
    # claude -p skips the trust prompt and reads .claude/settings.json from its
    # working directory, so a document folder could hand it hooks to run.
    repo = os.path.join(work, "docrepo")
    os.makedirs(os.path.join(repo, ".claude"))
    _write(os.path.join(repo, ".claude", "settings.json"), '{"hooks": {}}')
    cli = _stand_in(os.path.join(work, "bin"), _WHERE)
    monkeypatch.setenv(claude_cli.ENV_VAR, cli)
    monkeypatch.chdir(repo)
    r = claude_cli.run("p", "doc", timeout=60)
    cwd, listing = ast.literal_eval(r.stdout.strip())
    assert os.path.normcase(os.path.realpath(cwd)) != os.path.normcase(os.path.realpath(repo))
    assert listing == []
    assert not os.path.exists(cwd), "the private folder outlives the call"


@pytest.mark.skipif(not _WINDOWS, reason="the npm cmd shim runs only under cmd.exe")
def test_an_npm_shim_never_runs_a_node_planted_in_the_callers_folder(work, monkeypatch):
    # cmd.exe looks for the shim's bare "node" in the current directory first.
    npm = os.path.join(work, "npm")
    os.makedirs(os.path.join(npm, "node_modules", "@anthropic-ai", "claude-code"))
    shim = _write(os.path.join(npm, "claude.cmd"), _NPM_SHIM, newline="")
    node_dir = os.path.dirname(_stand_in(os.path.join(work, "nodejs"), _ECHO, name="node"))
    repo = os.path.join(work, "docrepo")
    os.makedirs(repo)
    marker = os.path.join(work, "PLANTED-RAN")
    _write(os.path.join(repo, "node.cmd"),
           f'@echo off\r\necho x> "{marker}"\r\necho PLANTED-NODE\r\n', newline="")
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setenv(claude_cli.ENV_VAR, shim)
    monkeypatch.setenv("PATH", node_dir + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.chdir(repo)
    r = claude_cli.run("the prompt", "the document", timeout=60)
    assert "PLANTED" not in r.stdout and not os.path.exists(marker)
    assert r.stdout.rstrip("\n").endswith("|the prompt|the document"), (r.stdout, r.stderr)


@pytest.mark.skipif(not _WINDOWS, reason="cmd.exe batch parsing exists only on Windows")
def test_a_bat_shim_is_handled_like_a_cmd_shim(monkeypatch, work):
    cmd = _stand_in(os.path.join(work, "bin"), _ECHO)
    bat = cmd[:-4] + ".bat"
    os.replace(cmd, bat)
    monkeypatch.setenv(claude_cli.ENV_VAR, bat)
    r = claude_cli.run("a\nb & c", "doc", timeout=60)
    assert r.stdout.rstrip("\n").endswith("|a\nb & c|doc")


def test_the_timeout_stops_the_whole_process_tree(monkeypatch, work):
    # A batch shim runs the CLI as a grandchild. Killing only the direct child
    # leaves the grandchild holding the pipes, and the call then waits for it.
    cli = _stand_in(os.path.join(work, "bin"), _SLEEP)
    monkeypatch.setenv(claude_cli.ENV_VAR, cli)
    start = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as info:
        claude_cli.run("p", "doc", timeout=1)
    assert time.monotonic() - start < 5
    assert work not in str(info.value), "the timeout message names the CLI path"


def _survives(wrapper, arg):
    # In the wrapper's folder, since a probe like "x>OS>y" writes a file named y.
    r = subprocess.run([wrapper, arg], capture_output=True, text=True, timeout=30,
                       cwd=os.path.dirname(wrapper))
    return r.stdout.strip() == repr([arg])


@pytest.mark.skipif(not _WINDOWS, reason="cmd.exe batch parsing exists only on Windows")
def test_the_refused_characters_are_exactly_the_ones_cmd_reinterprets(work):
    # A wrapper that runs %* inside a parenthesized block with delayed
    # expansion on sees every reading cmd.exe applies. Each punctuation
    # character goes through once in an argument Python leaves unquoted and
    # once in one it quotes. A quote on its own survives, but it flips cmd's
    # quote state, so the third probe pairs it with a space and an "&".
    body = _write(os.path.join(work, "argv.py"), "import sys\nprint(repr(sys.argv[1:]))\n")
    wrapper = _write(os.path.join(work, "wrap.cmd"),
                     f'@echo off\r\nsetlocal enabledelayedexpansion\r\nif 1==1 (\r\n'
                     f'  "{sys.executable}" "{body}" %*\r\n)\r\n', newline="")
    changed, changed_quoted = set(), set()
    for c in string.punctuation + "\r\n":
        if not _survives(wrapper, f"x{c}OS{c}y"):
            changed.add(c)
        if not _survives(wrapper, f"a {c}OS{c} b"):
            changed_quoted.add(c)
    if not _survives(wrapper, 'x" & echo y'):
        changed.add('"')
    assert changed | changed_quoted == claude_cli.CMD_UNSAFE | claude_cli.CMD_UNSAFE_UNQUOTED
    # A character in the unquoted set is refused only where Python leaves the
    # argument unquoted, so it must be harmless inside quotes.
    assert not claude_cli.CMD_UNSAFE_UNQUOTED & changed_quoted
