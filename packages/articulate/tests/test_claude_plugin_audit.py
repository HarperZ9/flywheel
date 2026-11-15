"""The built plugin's server, watched by Python's audit hooks for a whole session.

test_local_tools_stay_local.py patches the functions a tool could use to reach
the network, start a process or touch a file, in the test's own process. This
file checks the same claims from below, against the bundle Claude Code starts:
it launches the built server with the interpreter flags, environment and script
.mcp.json declares, behind a small harness that installs sys.addaudithook before
serve.py runs, then sends a session that calls every listed tool and every
hidden one. The interpreter reports each file open, directory listing, process,
socket and file change through the hook, from C code as well as Python.

A second session lists the hosted tools with the local-only switch still on,
which is what a user gets by editing the plugin's settings to list them: those
calls must be refused before the text reaches a temporary file.

The session passes when every file it opens is opened for reading and sits in
the plugin folder or the Python installation, every folder it lists is in one of
those, and no process, network, file-change or native-code event occurs. Three
controls plant a tool that removes a file, writes a file or opens a socket, and
each must fail the same check.
"""
import json
import os
import sys
from pathlib import Path

import pytest

from claude_plugin_helpers import PLUGIN_ENV, load
from articulate import host_edit, local_mcp

build = load("build_claude_plugin")
smoke = load("smoke_claude_plugin")

MARKER = "Zebracorn quartermaster 7319 leveraged a cutting-edge synergy."
# Event families that mean a process, the network, a file change or native code.
FORBIDDEN = ("socket.", "subprocess.", "os.system", "os.exec", "os.posix_spawn",
             "os.spawn", "os.startfile", "os.fork", "os.kill", "ctypes.", "urllib.",
             "http.", "os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.link",
             "os.symlink", "os.truncate", "os.chmod", "os.chown", "os.utime",
             "os.chdir", "shutil.", "tempfile.", "winreg.", "_winapi.", "os.putenv",
             "os.unsetenv", "webbrowser.", "sqlite3.", "ftplib.", "smtplib.", "glob.")

HARNESS = r'''
import sys
LOG = []
FORBIDDEN = %r
def hook(event, args):
    if event == "open":
        LOG.append(["open", args[0] if isinstance(args[0], int) else str(args[0]),
                    args[1], args[2] if len(args) > 2 else 0])
    elif event in ("os.listdir", "os.scandir"):
        LOG.append([event, str(args[0]), None, 0])
    elif event.startswith(FORBIDDEN):
        LOG.append([event, repr(args)[:200], None, 0])
sys.addaudithook(hook)
import os, runpy
serve, plant, scratch = sys.argv[1], sys.argv[2], sys.argv[3]
if plant != "none":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(serve)), "src"))
    import articulate.mcp_server as tools
    real = tools.do_score
    def planted(text):
        if plant == "remove":
            os.remove(scratch)
        elif plant == "write":
            open(scratch, "w").close()
        elif plant == "socket":
            import socket
            socket.socket().close()
        return real(text)
    tools.do_score = planted
sys.argv = [serve]
try:
    runpy.run_path(serve, run_name="__main__")
except SystemExit:
    pass
finally:
    import json
    prefixes = [sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix]
    sys.stderr.write("AUDIT " + json.dumps({"log": LOG, "prefixes": prefixes}) + "\n")
''' % (FORBIDDEN,)


@pytest.fixture(scope="module")
def plugin(tmp_path_factory):
    out = tmp_path_factory.mktemp("audit") / "articulate-writing"
    build.build(out)
    return out


def _requests():
    calls = [(t["name"], {name: MARKER for name in t["inputSchema"].get("required", [])})
             for t in local_mcp.listed_tools(PLUGIN_ENV)]
    plan = host_edit.edit_plan(MARKER)
    calls = [(name, {"text": MARKER, "rewrite": MARKER.replace("leveraged", "used"),
                     "plan_id": plan["plan_id"]} if name == "edit_submit" else args)
             for name, args in calls]
    calls += [(name, {"text": MARKER, "backend": backend})
              for name in ("fix", "judge", "polish")
              for backend in ("none", "anthropic", "ollama", "sampling")]
    reqs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    reqs += [{"jsonrpc": "2.0", "id": 3 + n, "method": "tools/call",
              "params": {"name": name, "arguments": args}}
             for n, (name, args) in enumerate(calls)]
    return reqs + [{"jsonrpc": "2.0", "id": 3 + len(calls), "method": "ping"}]


def _session(plugin, tmp_path, plant="none", extra_env=None):
    """Run one audited session; return (answers by id, audit record)."""
    harness = tmp_path / "audit_harness.py"
    harness.write_text(HARNESS, encoding="utf-8")
    scratch = tmp_path / "scratch.txt"
    scratch.write_text("scratch\n", encoding="utf-8")
    argv, env = smoke.launch_spec(plugin, command=sys.executable, extra_env=extra_env)
    assert argv[-1].endswith("server/serve.py")
    argv = argv[:-1] + [str(harness), argv[-1], plant, str(scratch)]
    work = tmp_path / "work"
    work.mkdir()
    import subprocess
    data = "".join(json.dumps(r) + "\n" for r in _requests()).encode("utf-8")
    run = subprocess.run(argv, input=data, env=env, cwd=work, capture_output=True,
                         timeout=120)
    answers = {m.get("id"): m for m in map(json.loads, run.stdout.decode("utf-8")
                                           .splitlines()) if m}
    line = [ln for ln in run.stderr.decode("utf-8", "replace").splitlines()
            if ln.startswith("AUDIT ")]
    assert line, run.stderr.decode("utf-8", "replace")[-2000:]
    return answers, json.loads(line[-1][len("AUDIT "):])


def _norm(path):
    return os.path.normcase(os.path.realpath(path))


def _allowed_place(path, roots):
    target = _norm(path)
    return any(target == r or target.startswith(r + os.sep) for r in roots)


def _writes(mode, flags):
    if isinstance(mode, str):
        return bool(set(mode) & set("wax+"))
    return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))


def violations(record, plugin, readable=()):
    """Every audited action outside what the plugin's README says the server does.
    readable adds folders the README says the server may read: the house-voice
    settings folder. A write there is still a violation."""
    roots = [_norm(plugin)] + [_norm(p) for p in record["prefixes"]] + [_norm(p) for p in readable]
    out = []
    for event, target, mode, flags in record["log"]:
        if event == "open":
            if isinstance(target, int) or _writes(mode, flags) or not _allowed_place(
                    target, roots):
                out.append(f"open {target} mode={mode} flags={flags}")
        elif event in ("os.listdir", "os.scandir"):
            if not _allowed_place(target, roots):
                out.append(f"{event} {target}")
        else:
            out.append(f"{event} {target}")
    return out


@pytest.mark.parametrize("extra_env", [None, {"ARTICULATE_MCP_TOOLS": "all"}],
                         ids=["plugin settings", "hosted tools listed, switch on"])
def test_a_whole_session_touches_nothing_outside_the_plugin_and_python(plugin, tmp_path,
                                                                       extra_env):
    answers, record = _session(plugin, tmp_path, extra_env=extra_env)
    expected_ids = {r["id"] for r in _requests() if "id" in r}
    assert set(answers) == expected_ids
    assert not any(a.get("error") for a in answers.values()), answers
    reads = [e for e in record["log"] if e[0] == "open"]
    assert any(_norm(plugin) in _norm(e[1]) for e in reads), "the hook saw no plugin read"
    from articulate import house_settings
    config = house_settings.config_dir()
    assert any(_norm(config) in _norm(e[1]) for e in reads), "the house settings read was not seen"
    assert violations(record, plugin, readable=[config]) == []
    assert list((tmp_path / "work").iterdir()) == []


def test_a_write_in_the_readable_settings_folder_is_still_a_violation(tmp_path):
    record = {"prefixes": [], "log": [["open", str(tmp_path / "house.json"), "w", 0]]}
    assert violations(record, tmp_path / "plugin", readable=[tmp_path])


@pytest.mark.parametrize("plant,expected", [("remove", "os.remove"),
                                            ("write", "open"),
                                            ("socket", "socket.")])
def test_a_planted_side_effect_fails_the_check(plugin, tmp_path, plant, expected):
    """Control: a score tool patched to act outside the plugin is caught."""
    answers, record = _session(plugin, tmp_path, plant)
    assert answers, "the planted session gave no answers"
    found = violations(record, plugin)
    assert any(v.startswith(expected) for v in found), found
