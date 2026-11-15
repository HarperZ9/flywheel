"""A stand-in named like an agent CLI, for the CLI tier tests.

It writes back what it received (argv, working folder and its listing, stdin,
environment) and answers. It also does what ``claude`` does with a project
settings file it is allowed to read: it runs the file's SessionStart hook,
which writes a marker. No model is reached.
"""
import json
import os
import shutil
import stat
import sys

WINDOWS = os.name == "nt"
FAKE_KEY = "sk-fake-planted-cli-key-0042"
SYSTEM32 = os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32")

# Writes what it saw to `record`, then answers. Emulates a project hook: unless
# told to read user settings only, it runs ./.claude/settings.json's command.
STAND_IN = r'''
import json, os, subprocess, sys
args = sys.argv[1:]
seen = {"args": args, "cwd": os.getcwd(), "listing": sorted(os.listdir(".")),
        "stdin": sys.stdin.read(), "env": dict(os.environ)}
user_only = "--setting-sources" in args and args[args.index("--setting-sources") + 1] == "user"
settings = os.path.join(".claude", "settings.json")
if not user_only and os.path.exists(settings):
    hook = json.load(open(settings))["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    subprocess.run(hook, shell=True)
with open(RECORD, "w", encoding="utf-8") as fh:
    json.dump(seen, fh)
if "--version" in args:
    print(VERSION)
else:
    print("STUB-ANSWER")
'''


def _write(path, text, newline=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)
    return path


def stand_in(folder, name, record, version="0.0.0"):
    body = _write(os.path.join(folder, name + "-body.py"),
                  f"RECORD = {record!r}\nVERSION = {version!r}\n" + STAND_IN)
    if WINDOWS:
        return _write(os.path.join(folder, name + ".cmd"),
                      f'@echo off\r\n"{sys.executable}" "{body}" %*\r\n', newline="")
    shim = _write(os.path.join(folder, name), f'#!/bin/sh\nexec "{sys.executable}" "{body}" "$@"\n')
    os.chmod(shim, os.stat(shim).st_mode | stat.S_IXUSR)
    return shim


def plant_binary(folder, name, marker):
    """A program named like the CLI in the server's folder. On Windows a copy of
    hostname.exe, which CreateProcess finds in the working folder by bare name."""
    os.makedirs(folder, exist_ok=True)
    if WINDOWS:
        src = os.path.join(SYSTEM32, "hostname.exe")
        shutil.copy(src, os.path.join(folder, name + ".exe"))
        return
    path = _write(os.path.join(folder, name), f'#!/bin/sh\necho x > "{marker}"\necho PLANTED\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)


def plant_script(folder, name, marker):
    """A script named like a program that writes `marker` and prints PLANTED if it
    ever runs. A batch file on Windows, so it wins only against other batch files."""
    if WINDOWS:
        return _write(os.path.join(folder, name + ".cmd"),
                      f'@echo off\r\necho x> "{marker}"\r\necho PLANTED\r\n', newline="")
    path = _write(os.path.join(folder, name), f'#!/bin/sh\necho x > "{marker}"\necho PLANTED\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


def make_world(tmp_path, monkeypatch):
    """A server folder holding a project settings hook, and a bin folder on PATH
    after a "." entry. Fake provider keys sit in the environment."""
    project, bindir = tmp_path / "project", tmp_path / "bin"
    marker = tmp_path / "HOOK-RAN"
    hook = f'"{sys.executable}" -c "open(r\'{marker}\', \'w\').write(\'x\')"'
    _write(str(project / ".claude" / "settings.json"), json.dumps(
        {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": hook}]}]}}))
    bindir.mkdir()
    path = [".", str(bindir)] + ([SYSTEM32] if WINDOWS else ["/usr/bin", "/bin"])
    monkeypatch.setenv("PATH", os.pathsep.join(path))
    for var in ("RELAY_CLAUDE_CLI", "RELAY_CODEX_CLI", "RELAY_ALLOW_EXEC_CLI", "RELAY_CHILD_ENV",
                "NoDefaultCurrentDirectoryInExePath"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.chdir(project)
    return {"project": project, "bin": bindir, "marker": marker, "tmp": tmp_path}
